import asyncio
import logging
import os
from typing import Any, Literal

import optuna
from models.load_test import SweepConfig, TuningConfig, TuningTrial
from services.event_broadcaster import EventBroadcaster
from services.k8s_operator import K8sOperator
from services.llm_assistant import get_llm_assistant
from services.shared import storage
from services.tuner_logic import (
    TunerLogic,
    _power_of_2_range,
    classify_failure_from_logs,
    execute_trial_for_tuner,
    finalize_tuning_for_tuner,
    handle_trial_result_for_tuner,
    save_auto_benchmark_for_tuner,
    update_pareto_front_for_tuner,
)

from .model_resolver import resolve_model_name

optuna.logging.set_verbosity(optuna.logging.WARNING)
OPTUNA_AVAILABLE = True
logger = logging.getLogger(__name__)


class AutoTuner:
    _K8S_PROXY_ATTRS = {
        "_k8s_available",
        "_k8s_apps",
        "_k8s_custom",
        "_is_args_snapshot",
        "_last_rollback_trial",
        "_wait_durations",
        "_total_wait_seconds",
        "_poll_count",
        "_cooldown_secs",
    }

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self._K8S_PROXY_ATTRS and "_k8s_operator" in self.__dict__:
            setattr(self.__dict__["_k8s_operator"], name, value)
            return
        super().__setattr__(name, value)

    def __getattr__(self, name: str) -> Any:
        if name in self._K8S_PROXY_ATTRS and "_k8s_operator" in self.__dict__:
            return getattr(self.__dict__["_k8s_operator"], name)
        raise AttributeError(name)

    def __init__(self, metrics_collector, load_engine) -> None:
        self._metrics = metrics_collector
        self._load_engine = load_engine
        self._k8s_operator = K8sOperator()
        self._event_broadcaster = EventBroadcaster()
        self._tuner_logic = TunerLogic(load_engine)
        self._trials: list[TuningTrial] = []
        self._best_trial: TuningTrial | None = None
        self._running = False
        self._cancel_event = asyncio.Event()
        self._study: optuna.Study | None = None
        self._direction = "maximize"
        self._vllm_endpoint = ""
        self._config: TuningConfig | None = None
        self._sweep_config: SweepConfig | None = None
        self.evaluation_mode: Literal["single", "sweep"] = "single"
        self._pareto_front_size: int | None = None
        self._best_score_history: list[float] = []
        self._k8s_core = None
        self._lock, self._study_lock, self._k8s_lock = asyncio.Lock(), asyncio.Lock(), asyncio.Lock()
        self._current_task: asyncio.Task[Any] | None = None

    @property
    def trials(self) -> list[TuningTrial]:
        return self._trials

    @property
    def best(self) -> TuningTrial | None:
        return self._best_trial

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def wait_metrics(self) -> dict[str, Any]:
        return self._k8s_operator.wait_metrics

    async def _wait_for_ready(self, timeout: int = 300, interval: int = 5) -> bool:
        return await self._k8s_operator.wait_for_ready(self._cancel_event, timeout=timeout, interval=interval)

    async def _preflight_check(self) -> dict[str, Any]:
        return await self._k8s_operator.preflight_check()

    async def subscribe(self) -> asyncio.Queue[Any]:
        return await self._event_broadcaster.subscribe()

    async def unsubscribe(self, q: asyncio.Queue[Any]) -> None:
        await self._event_broadcaster.unsubscribe(q)

    async def _broadcast(self, data: dict[str, Any]) -> None:
        await self._event_broadcaster.broadcast(data)

    async def _emit_trial_metrics(self, trial_start: float, status: str) -> None:
        await self._event_broadcaster.emit_trial_metrics(trial_start, status, self._best_trial, self._config)

    async def _broadcast_persistence_warning_once(self) -> None:
        await self._event_broadcaster.broadcast_persistence_warning_once()

    def _params_to_args(self, params: dict[str, Any]) -> list[str]:
        return self._k8s_operator.params_to_args(params)

    async def _apply_params(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._k8s_operator.apply_params(params, self._k8s_lock)

    async def _rollback_to_snapshot(self, trial_num: int) -> bool:
        return await self._k8s_operator.rollback_to_snapshot(trial_num, self._k8s_lock)

    def _save_trial_fn(self):
        return storage.save_trial

    def _suggest_params(self, trial, config: TuningConfig) -> dict[str, Any]:
        return self._tuner_logic.suggest_params(trial, config)

    async def _evaluate(
        self, endpoint: str, config: TuningConfig, trial=None, trial_num: int = 0, broadcaster=None
    ) -> tuple[float, float, float]:
        return await self._tuner_logic.evaluate(
            endpoint,
            config,
            trial=trial,
            trial_num=trial_num,
            broadcaster=self._event_broadcaster,
            model_resolver=resolve_model_name,
        )

    async def _objective(
        self, endpoint: str, config: TuningConfig, trial=None, trial_num: int = 0
    ) -> tuple[float, float, float]:
        return await self._tuner_logic.objective(
            endpoint,
            config,
            evaluation_mode=self.evaluation_mode,
            sweep_config=self._sweep_config,
            trial=trial,
            trial_num=trial_num,
            broadcaster=self._event_broadcaster,
            evaluate_fn=self._evaluate,
        )

    async def _init_tuning_state(self, config: TuningConfig) -> None:
        self._config, self._trials, self._best_score_history, self._best_trial = config, [], [], None
        self._pareto_front_size = None
        self._event_broadcaster.reset_persistence_warning()
        self._direction, self._study = await self._tuner_logic.setup_study(
            config, os.getenv("OPTUNA_STORAGE_URL"), broadcaster=self._event_broadcaster
        )

    async def _initialize_start_state(
        self, config: TuningConfig, evaluation_mode: Literal["single", "sweep"], sweep_config: SweepConfig | None
    ) -> tuple[bool, int | None, dict[str, Any] | None]:
        running_row_id: int | None = None
        async with self._lock:
            if self._running:
                return False, None, {"error": "이미 튜닝이 실행 중입니다."}
            if not OPTUNA_AVAILABLE:
                return False, None, {"error": "optuna 패키지가 필요합니다: pip install optuna"}
            if self._cancel_event.is_set():
                await asyncio.sleep(0.1)
            self._cancel_event.clear()
            self._running = True
            self.evaluation_mode = evaluation_mode
            self._sweep_config = sweep_config.model_copy(deep=True) if sweep_config is not None else None
            try:
                running_row_id = await storage.set_running("tuner")
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning("[AutoTuner] Failed to record running state: %s", e)
            await self._init_tuning_state(config)
        return True, running_row_id, None

    async def _validate_preflight(self, skip_preflight: bool) -> dict[str, Any] | None:
        if skip_preflight:
            return None
        preflight = await self._preflight_check()
        if preflight["success"]:
            return None
        error_msg, error_type = (
            preflight.get("error", "Preflight 검증 실패"),
            preflight.get("error_type", "preflight_error"),
        )
        await self._broadcast({"type": "tuning_error", "data": {"error": error_msg, "error_type": error_type}})
        return {"error": error_msg, "error_type": error_type}

    async def _validate_initial_readiness(self) -> dict[str, Any] | None:
        if await self._wait_for_ready(timeout=60, interval=5):
            return None
        return (
            {"error": "튜닝이 취소되었습니다."}
            if self._cancel_event.is_set()
            else {"error": "InferenceService가 준비되지 않았습니다. 튜닝을 시작할 수 없습니다."}
        )

    async def _apply_trial_params(self, trial, trial_num: int, params: dict[str, Any]) -> bool:
        await self._broadcast({"type": "phase", "data": {"trial_id": trial_num, "phase": "applying_config"}})
        apply_result = await self._apply_params(params)
        if apply_result["success"]:
            return True
        async with self._study_lock:
            assert self._study is not None
            self._study.tell(trial, state=optuna.trial.TrialState.FAIL)
        await self._broadcast(
            {
                "type": "tuning_error",
                "data": {
                    "error": apply_result.get("error", "InferenceService 파라미터 적용 실패"),
                    "error_type": apply_result.get("error_type", "apply_failed"),
                },
            }
        )
        self._cancel_event.set()
        async with self._lock:
            self._running = False
        return False

    async def _wait_for_isvc_ready(self, trial, trial_num: int) -> bool:
        if await self._wait_for_ready():
            return True
        if self._cancel_event.is_set():
            return False
        await self._broadcast(
            {"type": "tuning_warning", "data": {"message": "IS가 준비되지 않아 롤백합니다", "trial": trial_num}}
        )
        await self._rollback_to_snapshot(trial_num)
        startup_logs: str | None = None
        failure_reason = "startup_timeout"
        try:
            startup_logs = await self._read_failure_logs()
            failure_reason = classify_failure_from_logs(startup_logs) if startup_logs else "startup_timeout"
            trial.set_user_attr("failure_reason", failure_reason)
            logger.debug("[AutoTuner] Trial %d startup failure classified as: %s", trial_num, failure_reason)
        except Exception:
            pass
        try:
            await self._explain_failure(trial_num, trial.params, failure_reason, startup_logs)
        except Exception as e:
            logger.debug("[AutoTuner] Startup failure explanation call failed: %s", e)
        async with self._study_lock:
            assert self._study is not None
            self._study.tell(trial, state=optuna.trial.TrialState.FAIL)
        return False

    async def _run_trial_evaluation(self, trial, trial_num: int) -> tuple[Any, ...]:
        assert self._config is not None
        return await self._objective(self._vllm_endpoint, self._config, trial=trial, trial_num=trial_num)

    async def _update_pareto_front(self) -> None:
        await update_pareto_front_for_tuner(self)

    async def _handle_trial_result(self, trial, trial_num: int, score, tps, p99_lat, trial_start, params) -> bool:
        return await handle_trial_result_for_tuner(
            self,
            trial,
            trial_num,
            score,
            tps,
            p99_lat,
            trial_start,
            params,
            save_trial_fn=self._save_trial_fn(),
        )

    async def _execute_trial(self, trial_num: int, config: TuningConfig) -> None:
        await execute_trial_for_tuner(self, trial_num, config)

    async def _save_auto_benchmark(self) -> int | None:
        return await save_auto_benchmark_for_tuner(
            self,
            model_resolver=resolve_model_name,
            save_benchmark_fn=storage.save_benchmark,
        )

    async def _finalize_tuning(self, auto_benchmark: bool = False) -> int | None:
        return await finalize_tuning_for_tuner(self, auto_benchmark=auto_benchmark)

    async def _read_failure_logs(self) -> str | None:
        return await self._k8s_operator.get_pod_logs()

    async def _generate_report(self) -> None:
        if self._config is None or not self._config.enable_llm_assistant:
            return
        if self._best_trial is None or not self._trials:
            return
        failure_breakdown: dict[str, int] = {}
        status_counts = {"completed": 0, "failed": 0, "pruned": 0}
        try:
            for ft in self._study.trials if self._study is not None else []:
                reason = ft.user_attrs.get("failure_reason") if hasattr(ft, "user_attrs") else None
                if reason:
                    failure_breakdown[reason] = failure_breakdown.get(reason, 0) + 1
        except Exception as e:
            logger.debug("[AutoTuner] Report failure_breakdown scan failed: %s", e)
        for t in self._trials:
            if getattr(t, "pruned", False):
                status_counts["pruned"] += 1
            elif t.status == "completed":
                status_counts["completed"] += 1
            else:
                status_counts["failed"] += 1
        try:
            importance = await self.get_importance()
        except Exception:
            importance = {}
        summary: dict[str, Any] = {
            "objective": self._config.objective,
            "best_params": self._best_trial.params,
            "best_tps": self._best_trial.tps,
            "best_p99_latency_ms": self._best_trial.p99_latency * 1000,
            "best_score": self._best_trial.score,
            "total_trials": len(self._trials),
            "status_counts": status_counts,
            "failure_breakdown": failure_breakdown,
            "parameter_importance": {k: round(v, 4) for k, v in list(importance.items())[:5]},
            "pareto_front_size": self._pareto_front_size,
            "model_architecture": {
                "num_hidden_layers": self._config.model_num_layers,
                "num_key_value_heads": self._config.model_num_kv_heads,
                "head_dim": self._config.model_head_dim,
                "max_position_embeddings": self._config.model_max_position_embeddings,
                "weight_size_gib": self._config.model_weight_gib,
            },
        }
        try:
            report = await get_llm_assistant().generate_tuning_report(
                endpoint=self._vllm_endpoint, summary=summary
            )
        except Exception as e:
            logger.debug("[AutoTuner] Report generation failed: %s", e)
            return
        if report:
            await self._broadcast({"type": "tuning_report", "data": {"markdown": report, "summary": summary}})

    async def _explain_failure(
        self, trial_num: int, params: dict[str, Any], failure_reason: str, logs: str | None
    ) -> None:
        if self._config is None or not self._config.enable_llm_assistant:
            return
        try:
            explanation = await get_llm_assistant().summarize_failure(
                endpoint=self._vllm_endpoint,
                params=params,
                failure_reason=failure_reason,
                logs=logs,
            )
        except Exception as e:
            logger.debug("[AutoTuner] Failure explanation call failed: %s", e)
            return
        if explanation:
            await self._broadcast(
                {
                    "type": "tuning_failure_explanation",
                    "data": {"trial_id": trial_num, "reason": failure_reason, "explanation": explanation},
                }
            )

    def _sanitize_suggestion(self, suggestion: dict[str, Any], config: TuningConfig) -> dict[str, Any] | None:
        try:
            max_len_upper = config.max_model_len_range[1]
            if config.model_max_position_embeddings:
                max_len_upper = min(max_len_upper, config.model_max_position_embeddings)
            len_choices = _power_of_2_range(config.max_model_len_range[0], max_len_upper)

            mns = int(suggestion.get("max_num_seqs", config.max_num_seqs_range[0]))
            mns = max(config.max_num_seqs_range[0], min(config.max_num_seqs_range[1], mns))
            mns = (mns // 32) * 32 or config.max_num_seqs_range[0]

            gmu = float(suggestion.get("gpu_memory_utilization", config.gpu_memory_utilization_range[0]))
            gmu = max(config.gpu_memory_utilization_range[0], min(config.gpu_memory_utilization_range[1], gmu))

            mml_raw = int(suggestion.get("max_model_len", len_choices[0]))
            mml = min(len_choices, key=lambda v: abs(v - mml_raw))

            mnbt_raw = int(suggestion.get("max_num_batched_tokens", config.max_num_batched_tokens_range[0]))
            batched_low = max(config.max_num_batched_tokens_range[0], mns)
            batched_low = -(-batched_low // 256) * 256
            batched_high = max(config.max_num_batched_tokens_range[1], batched_low)
            batched_high = (batched_high // 256) * 256
            mnbt = max(batched_low, min(batched_high, mnbt_raw))
            mnbt = (mnbt // 256) * 256 or batched_low

            clean: dict[str, Any] = {
                "max_num_seqs": mns,
                "gpu_memory_utilization": gmu,
                "max_model_len": mml,
                "max_num_batched_tokens": mnbt,
                "enable_chunked_prefill": bool(suggestion.get("enable_chunked_prefill", False)),
                "enable_enforce_eager": bool(suggestion.get("enable_enforce_eager", False)),
            }
            if config.block_size_options:
                bs_raw = suggestion.get("block_size", config.block_size_options[0])
                clean["block_size"] = (
                    int(bs_raw) if int(bs_raw) in config.block_size_options else config.block_size_options[0]
                )
            if config.include_swap_space:
                sws = float(suggestion.get("swap_space", config.swap_space_range[0]))
                clean["swap_space"] = max(config.swap_space_range[0], min(config.swap_space_range[1], sws))
            return clean
        except (ValueError, TypeError, KeyError) as e:
            logger.debug("[AutoTuner] Warmup suggestion sanitize failed: %s (input=%s)", e, suggestion)
            return None

    async def _run_warmup_suggestions(self, config: TuningConfig) -> None:
        if not config.enable_llm_assistant or self._study is None:
            return
        model_info = {
            "num_hidden_layers": config.model_num_layers,
            "num_key_value_heads": config.model_num_kv_heads,
            "head_dim": config.model_head_dim,
            "kv_dtype_bytes": config.model_kv_dtype_bytes,
            "max_position_embeddings": config.model_max_position_embeddings,
            "weight_size_gib": config.model_weight_gib,
        }
        search_space = {
            "max_num_seqs": {"min": config.max_num_seqs_range[0], "max": config.max_num_seqs_range[1], "step": 32},
            "gpu_memory_utilization": {
                "min": config.gpu_memory_utilization_range[0],
                "max": config.gpu_memory_utilization_range[1],
            },
            "max_model_len": {
                "min": config.max_model_len_range[0],
                "max": config.max_model_len_range[1],
                "note": "power-of-2 preferred",
            },
            "max_num_batched_tokens": {
                "min": config.max_num_batched_tokens_range[0],
                "max": config.max_num_batched_tokens_range[1],
                "step": 256,
            },
            "block_size": {"choices": config.block_size_options},
            "enable_chunked_prefill": {"choices": [True, False]},
            "enable_enforce_eager": {"choices": [True, False]},
        }
        hw_context = {"pod_memory_gib": config.pod_memory_gib, "runtime": "OpenVINO or CUDA"}
        try:
            suggestions = await get_llm_assistant().suggest_warmup_params(
                endpoint=self._vllm_endpoint,
                model_info=model_info,
                search_space=search_space,
                hw_context=hw_context,
                count=3,
            )
        except Exception as e:
            logger.debug("[AutoTuner] Warmup suggestion call failed: %s", e)
            return
        if not suggestions:
            return
        enqueued: list[dict[str, Any]] = []
        for s in suggestions:
            clean = self._sanitize_suggestion(s, config)
            if clean is not None:
                try:
                    self._study.enqueue_trial(clean, skip_if_exists=True)
                    enqueued.append(clean)
                except Exception as e:
                    logger.debug("[AutoTuner] enqueue_trial failed: %s", e)
        if enqueued:
            logger.info("[AutoTuner] LLM warmup enqueued %d configurations", len(enqueued))
            await self._broadcast(
                {"type": "tuning_warmup_suggestions", "data": {"count": len(enqueued), "configurations": enqueued}}
            )

    async def get_cr_context(self) -> tuple[dict[str, Any] | None, Any]:
        """Return (cr_spec, cr_adapter) without exposing _k8s_operator internals."""
        cr_spec = await self._k8s_operator.read_current_spec()
        return cr_spec, self._k8s_operator._cr_adapter

    async def start(
        self,
        config: TuningConfig,
        vllm_endpoint: str,
        auto_benchmark: bool = False,
        skip_preflight: bool = False,
        evaluation_mode: Literal["single", "sweep"] = "single",
        sweep_config: SweepConfig | None = None,
    ) -> dict[str, Any]:
        state_initialized, running_row_id = False, None
        try:
            state_initialized, running_row_id, init_error = await self._initialize_start_state(
                config, evaluation_mode, sweep_config
            )
            if init_error is not None:
                return init_error
            self._vllm_endpoint = vllm_endpoint
            if config.served_model_name_warning:
                await self._broadcast({"type": "tuning_warning", "data": {"message": config.served_model_name_warning}})
            preflight_error = await self._validate_preflight(skip_preflight)
            if preflight_error is not None:
                return preflight_error
            readiness_error = await self._validate_initial_readiness()
            if readiness_error is not None:
                return readiness_error
            await self._run_warmup_suggestions(config)
            for trial_num in range(config.n_trials):
                if self._cancel_event.is_set() or not self._running:
                    break
                await self._execute_trial(trial_num=trial_num, config=config)
            if self._cancel_event.is_set():
                await self._broadcast({"type": "tuning_stopped", "data": {"total_trials": len(self._trials)}})
                return {
                    "completed": False,
                    "stopped": True,
                    "best_params": self._best_trial.params if self._best_trial else {},
                    "best_score": self._best_trial.score if self._best_trial else 0,
                    "trials": len(self._trials),
                }
            benchmark_id = await self._finalize_tuning(auto_benchmark=auto_benchmark)
            await self._generate_report()
            result: dict[str, Any] = {
                "completed": True,
                "best_params": self._best_trial.params if self._best_trial else {},
                "best_score": self._best_trial.score if self._best_trial else 0,
                "trials": len(self._trials),
            }
            if benchmark_id is not None:
                result["benchmark_id"] = benchmark_id
            return result
        finally:
            if state_initialized:
                current_task = asyncio.current_task()
                async with self._lock:
                    self._running = False
                    if self._current_task is current_task:
                        self._current_task = None
                if running_row_id is not None:
                    try:
                        await storage.clear_running(running_row_id)
                    except (OSError, RuntimeError, ValueError) as e:
                        logger.warning("[AutoTuner] Failed to clear running state: %s", e)

    async def stop(self) -> dict[str, Any]:
        async with self._lock:
            if not self._running:
                return {"success": False, "message": "No tuning is currently running."}
            self._cancel_event.set()
            self._running = False
            pending_task = self._current_task
        if pending_task and not pending_task.done() and pending_task is not asyncio.current_task():
            try:
                await asyncio.wait_for(asyncio.shield(pending_task), timeout=10.0)
            except (TimeoutError, asyncio.CancelledError):
                pending_task.cancel()
            except (RuntimeError, ValueError, OSError) as exc:
                logger.warning("[AutoTuner] Pending tuning task failed during stop: %s", exc)
        async with self._lock:
            if self._current_task is pending_task and pending_task is not None and pending_task.done():
                self._current_task = None
        return {"success": True, "message": "Tuning stopped."}

    async def get_importance(self) -> dict[str, Any]:
        return await self._tuner_logic.get_importance(self._study, self._trials)  # type: ignore[arg-type]
