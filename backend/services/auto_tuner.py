import asyncio
import logging
import os
from typing import Any, Literal

import optuna
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from models.load_test import SweepConfig, TuningConfig, TuningTrial
from services.event_broadcaster import EventBroadcaster
from services.k8s_operator import K8sOperator, _get_k8s_namespace, _get_vllm_is_name
from services.shared import storage
from services.tuner_logic import (
    TunerLogic,
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
_ = (k8s_client, k8s_config, _get_k8s_namespace, _get_vllm_is_name)


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
            preflight_error = await self._validate_preflight(skip_preflight)
            if preflight_error is not None:
                return preflight_error
            readiness_error = await self._validate_initial_readiness()
            if readiness_error is not None:
                return readiness_error
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
