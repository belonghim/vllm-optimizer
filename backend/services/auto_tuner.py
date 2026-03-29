"""
자동 파라미터 튜너 — Bayesian Optimization으로 최적 vLLM 설정 탐색
목표: 처리량(TPS) 최대화, 레이턴시(P99) 최소화
"""

import asyncio
import logging
import math
import os
import time
from typing import Any, Literal

import httpx
import optuna
from errors import TunerError  # pyright: ignore[reportImplicitRelativeImport]
from kubernetes import client as k8s_client
from models.load_test import (  # pyright: ignore[reportImplicitRelativeImport]
    Benchmark,
    LatencyStats,
    LoadTestConfig,
    LoadTestResult,
    SweepConfig,
    TpsStats,
    TuningConfig,
    TuningTrial,
)
from services.event_broadcaster import EventBroadcaster  # pyright: ignore[reportImplicitRelativeImport,reportMissingImports]
from services.k8s_operator import K8sOperator, _get_k8s_namespace, _get_vllm_is_name  # pyright: ignore[reportImplicitRelativeImport]
from services.shared import storage  # pyright: ignore[reportImplicitRelativeImport]

from .model_resolver import resolve_model_name

optuna.logging.set_verbosity(optuna.logging.WARNING)
OPTUNA_AVAILABLE = True

logger = logging.getLogger(__name__)


class AutoTuner:
    def __init__(self, metrics_collector, load_engine) -> None:
        self._metrics = metrics_collector
        self._load_engine = load_engine
        self._trials: list[TuningTrial] = []
        self._best_trial: TuningTrial | None = None
        self._running = False
        self._cancel_event = asyncio.Event()
        self._study: optuna.Study | None = None
        self._direction: str = "maximize"
        self._vllm_endpoint: str = ""
        self.evaluation_mode: Literal["single", "sweep"] = "single"
        self._sweep_config: SweepConfig | None = None
        self._config: TuningConfig | None = None  # Set in start()
        self._k8s_operator = K8sOperator()
        self._event_broadcaster = EventBroadcaster()
        self._k8s_core: k8s_client.CoreV1Api | None = None
        self._cooldown_secs: int = 30
        self._pareto_front_size: int | None = None
        self._lock = asyncio.Lock()
        self._study_lock = asyncio.Lock()
        self._k8s_lock = asyncio.Lock()
        self._best_score_history: list[float] = []
        self._current_task: asyncio.Task[Any] | None = None
        self._k8s_apps = self._k8s_operator._k8s_apps
        self._k8s_custom = self._k8s_operator._k8s_custom

    @property
    def _k8s_available(self) -> bool:
        return self._k8s_operator.k8s_available

    @_k8s_available.setter
    def _k8s_available(self, value: bool) -> None:
        self._k8s_operator._k8s_available = value

    @property
    def _k8s_apps(self):
        return self._k8s_operator._k8s_apps

    @_k8s_apps.setter
    def _k8s_apps(self, value) -> None:
        self._k8s_operator._k8s_apps = value

    @property
    def _k8s_custom(self):
        return self._k8s_operator._k8s_custom

    @_k8s_custom.setter
    def _k8s_custom(self, value) -> None:
        self._k8s_operator._k8s_custom = value

    @property
    def _is_args_snapshot(self) -> Any:
        return self._k8s_operator._is_args_snapshot

    @_is_args_snapshot.setter
    def _is_args_snapshot(self, value: Any) -> None:
        self._k8s_operator._is_args_snapshot = value

    @property
    def _last_rollback_trial(self) -> int | None:
        return self._k8s_operator._last_rollback_trial

    @_last_rollback_trial.setter
    def _last_rollback_trial(self, value: int | None) -> None:
        self._k8s_operator._last_rollback_trial = value

    @property
    def _wait_durations(self) -> list[float]:
        return self._k8s_operator._wait_durations

    @_wait_durations.setter
    def _wait_durations(self, value: list[float]) -> None:
        self._k8s_operator._wait_durations = value

    @property
    def _total_wait_seconds(self) -> float:
        return self._k8s_operator._total_wait_seconds

    @_total_wait_seconds.setter
    def _total_wait_seconds(self, value: float) -> None:
        self._k8s_operator._total_wait_seconds = value

    @property
    def _poll_count(self) -> int:
        return self._k8s_operator._poll_count

    @_poll_count.setter
    def _poll_count(self, value: int) -> None:
        self._k8s_operator._poll_count = value

    @property
    def _cooldown_secs(self) -> int:
        return self._k8s_operator._cooldown_secs

    @_cooldown_secs.setter
    def _cooldown_secs(self, value: int) -> None:
        self._k8s_operator._cooldown_secs = value

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

    async def _init_tuning_state(self, config: TuningConfig) -> None:
        self._config = config
        self._trials = []
        self._best_score_history = []
        self._best_trial = None
        self._pareto_front_size = None
        self._event_broadcaster.reset_persistence_warning()
        storage_url = os.getenv("OPTUNA_STORAGE_URL")
        self._direction, self._study = await self._setup_study(config, storage_url)

    async def start(
        self,
        config: TuningConfig,
        vllm_endpoint: str,
        auto_benchmark: bool = False,
        skip_preflight: bool = False,
        evaluation_mode: Literal["single", "sweep"] = "single",
        sweep_config: SweepConfig | None = None,
    ) -> dict[str, Any]:
        state_initialized = False
        _running_row_id: int | None = None
        try:
            state_initialized, _running_row_id, init_error = await self._initialize_start_state(
                config=config,
                evaluation_mode=evaluation_mode,
                sweep_config=sweep_config,
            )
            if init_error is not None:
                return init_error

            self._vllm_endpoint = vllm_endpoint
            preflight_error = await self._validate_preflight(skip_preflight=skip_preflight)
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
                await self._broadcast(
                    {
                        "type": "tuning_stopped",
                        "data": {
                            "total_trials": len(self._trials),
                        },
                    }
                )
                return {
                    "completed": False,
                    "stopped": True,
                    "best_params": self._best_trial.params if self._best_trial else {},
                    "best_score": self._best_trial.score if self._best_trial else 0,
                    "trials": len(self._trials),
                }

            benchmark_id = await self._finalize_tuning(auto_benchmark=auto_benchmark)

            response: dict[str, Any] = {
                "completed": True,
                "best_params": self._best_trial.params if self._best_trial else {},
                "best_score": self._best_trial.score if self._best_trial else 0,
                "trials": len(self._trials),
            }
            if benchmark_id is not None:
                response["benchmark_id"] = benchmark_id
            return response
        finally:
            if state_initialized:
                current_task = asyncio.current_task()
                async with self._lock:
                    self._running = False
                    if self._current_task is current_task:
                        self._current_task = None
                if _running_row_id is not None:
                    try:
                        await storage.clear_running(_running_row_id)
                    except (OSError, RuntimeError, ValueError) as e:
                        logger.warning("[AutoTuner] Failed to clear running state: %s", e)

    async def _initialize_start_state(
        self,
        config: TuningConfig,
        evaluation_mode: Literal["single", "sweep"],
        sweep_config: SweepConfig | None,
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

        logger.info("[AutoTuner] 튜닝 시작 전 K8s 권한 사전 검증 중...")
        preflight = await self._preflight_check()
        if preflight["success"]:
            return None

        error_msg = preflight.get("error", "Preflight 검증 실패")
        error_type = preflight.get("error_type", "preflight_error")
        await self._broadcast(
            {
                "type": "tuning_error",
                "data": {"error": error_msg, "error_type": error_type},
            }
        )
        return {"error": error_msg, "error_type": error_type}

    async def _validate_initial_readiness(self) -> dict[str, Any] | None:
        logger.info("[AutoTuner] 튜닝 시작 전 InferenceService 상태 확인 중...")
        if await self._wait_for_ready(timeout=60, interval=5):
            return None
        if self._cancel_event.is_set():
            return {"error": "튜닝이 취소되었습니다."}
        return {"error": "InferenceService가 준비되지 않았습니다. 튜닝을 시작할 수 없습니다."}

    async def _execute_trial(self, trial_num: int, config: TuningConfig) -> None:
        async with self._study_lock:
            assert self._study is not None
            trial = self._study.ask()
        params = self._suggest_params(trial, config)
        trial_start = time.monotonic()

        await self._broadcast(
            {
                "type": "trial_start",
                "data": {"trial_id": trial_num, "params": params},
            }
        )

        if not await self._apply_trial_params(trial, trial_num, params):
            return

        await self._broadcast(
            {
                "type": "phase",
                "data": {"trial_id": trial_num, "phase": "restarting"},
            }
        )
        await self._broadcast(
            {
                "type": "phase",
                "data": {"trial_id": trial_num, "phase": "waiting_ready"},
            }
        )

        if not await self._wait_for_isvc_ready(trial, trial_num):
            return

        try:
            score, tps, p99_lat = await self._run_trial_evaluation(trial, trial_num)
        except Exception as e:  # intentional: per-trial evaluation failure must not abort entire tuning session
            logger.warning("[AutoTuner] Trial %d evaluation failed: %s", trial_num, e)
            await self._broadcast(
                {
                    "type": "error",
                    "data": {
                        "message": f"Trial {trial_num} evaluation failed: {e}",
                        "recoverable": True,
                        "timestamp": time.time(),
                    },
                }
            )
            await self._broadcast(
                {
                    "type": "tuning_warning",
                    "data": {
                        "message": "트라이얼 평가 실패로 다음 트라이얼로 진행합니다",
                        "trial": trial_num,
                    },
                }
            )
            async with self._study_lock:
                assert self._study is not None
                self._study.tell(trial, state=optuna.trial.TrialState.FAIL)
            return

        await self._handle_trial_result(trial, trial_num, score, tps, p99_lat, trial_start, params)

    async def _setup_study(self, config: TuningConfig, storage_url: str | None) -> tuple[str, optuna.Study]:
        """Optuna study 초기화 및 반환."""
        direction = "maximize"
        if config.objective == "pareto":
            sampler = optuna.samplers.NSGAIISampler(seed=42)
            pruner = optuna.pruners.NopPruner()
            _study_name = "vllm-tuner-pareto"
            direction_kwarg: dict[str, Any] = {"directions": ["maximize", "minimize"]}
        else:
            direction = "maximize" if config.objective == "tps" else "minimize"
            sampler = optuna.samplers.TPESampler(seed=42)
            pruner = optuna.pruners.MedianPruner(n_startup_trials=3, n_warmup_steps=0)
            _study_name = f"vllm-tuner-{config.objective}"
            direction_kwarg = {"direction": direction}

        if storage_url:
            try:
                storage = await asyncio.to_thread(
                    optuna.storages.RDBStorage,
                    storage_url,
                    engine_kwargs={"connect_args": {"check_same_thread": False}},
                )
                study = await asyncio.to_thread(  # type: ignore[arg-type]
                    optuna.create_study,
                    sampler=sampler,
                    pruner=pruner,
                    storage=storage,
                    study_name=_study_name,
                    load_if_exists=True,
                    **direction_kwarg,
                )
                logger.info("[AutoTuner] Using SQLite storage: %s (study: %s)", storage_url, _study_name)
                if study.best_trials:
                    best_params = study.best_trial.params
                    study.enqueue_trial(params=best_params)
                    logger.info("[AutoTuner] Warm-start: enqueued previous best params: %s", best_params)
            except Exception as e:  # intentional: storage fallback (SQLAlchemy/Optuna errors too diverse)
                logger.warning("[AutoTuner] SQLite storage failed, falling back to in-memory: %s", e)
                await self._broadcast(
                    {
                        "type": "tuning_warning",
                        "data": {
                            "message": "스토리지 초기화 실패, 인메모리 모드로 실행합니다",
                        },
                    }
                )
                try:
                    study = optuna.create_study(sampler=sampler, pruner=pruner, **direction_kwarg)  # type: ignore[arg-type]
                except optuna.exceptions.OptunaError as e:
                    raise TunerError(
                        "Optuna study initialization failed after storage fallback",
                        detail={"storage_url": storage_url, "objective": config.objective},
                    ) from e
        else:
            try:
                study = optuna.create_study(sampler=sampler, pruner=pruner, **direction_kwarg)  # type: ignore[arg-type]
            except optuna.exceptions.OptunaError as e:
                raise TunerError(
                    "Optuna study initialization failed",
                    detail={"storage_url": storage_url, "objective": config.objective},
                ) from e

        return direction, study

    async def _apply_trial_params(self, trial, trial_num: int, params: dict[str, Any]) -> bool:
        """InferenceService args 업데이트. 실패 시 Optuna FAIL 처리 후 False 반환."""
        await self._broadcast(
            {
                "type": "phase",
                "data": {"trial_id": trial_num, "phase": "applying_config"},
            }
        )
        apply_result = await self._apply_params(params)
        if not apply_result["success"]:
            async with self._study_lock:
                assert self._study is not None
                self._study.tell(trial, state=optuna.trial.TrialState.FAIL)
            error_type = apply_result.get("error_type", "apply_failed")
            if error_type in {"rbac", "not_found"}:
                error_msg = apply_result.get("error", "InferenceService 접근/패치 오류")
                await self._broadcast(
                    {
                        "type": "tuning_error",
                        "data": {"error": error_msg, "error_type": error_type},
                    }
                )
                self._cancel_event.set()
                async with self._lock:
                    self._running = False
                return False

            error_msg = apply_result.get("error", "InferenceService 파라미터 적용 실패")
            await self._broadcast(
                {
                    "type": "tuning_error",
                    "data": {"error": error_msg, "error_type": error_type},
                }
            )
            self._cancel_event.set()
            async with self._lock:
                self._running = False
            return False
        return True

    async def _wait_for_isvc_ready(self, trial, trial_num: int) -> bool:
        """IS 준비 대기. 실패 시 rollback 및 Optuna FAIL 처리 후 False 반환."""
        ready = await self._wait_for_ready()
        if not ready:
            if self._cancel_event.is_set():
                logger.info("[AutoTuner] Trial %d: wait cancelled", trial_num)
                return False
            logger.warning("[AutoTuner] Trial %d: InferenceService not ready, rolling back", trial_num)
            await self._broadcast(
                {
                    "type": "tuning_warning",
                    "data": {
                        "message": "IS가 준비되지 않아 롤백합니다",
                        "trial": trial_num,
                    },
                }
            )
            await self._rollback_to_snapshot(trial_num)
            async with self._study_lock:
                assert self._study is not None
                self._study.tell(trial, state=optuna.trial.TrialState.FAIL)
            return False
        return True

    async def _rollback_config(self, trial_num: int) -> bool:
        """InferenceService args rollback (_rollback_to_snapshot의 named alias)."""
        return await self._rollback_to_snapshot(trial_num)

    async def _run_trial_evaluation(self, trial, trial_num: int) -> tuple[Any, ...]:
        """트라이얼 성능 평가 실행. (score, tps, p99_lat) 반환."""
        assert self._config is not None
        return await self._objective(self._vllm_endpoint, self._config, trial=trial, trial_num=trial_num)

    async def _objective(
        self,
        endpoint: str,
        config: TuningConfig,
        trial=None,
        trial_num: int = 0,
    ) -> tuple[float, float, float]:
        if self.evaluation_mode == "sweep":
            if self._sweep_config is None:
                raise TunerError(
                    "Sweep evaluation requires sweep_config",
                    detail={"evaluation_mode": self.evaluation_mode},
                )
            _trial_id = trial.number if trial is not None and hasattr(trial, "number") else trial_num
            await self._broadcast(
                {
                    "type": "phase",
                    "data": {"trial_id": _trial_id, "phase": "evaluating"},
                }
            )
            sweep_result = await self._load_engine.run_sweep(self._sweep_config)
            score = float(sweep_result.optimal_rps or 0.0)
            if trial is not None and config.objective != "pareto":
                trial.report(score, step=0)
            return score, score, 0.0

        return await self._evaluate(endpoint, config, trial=trial, trial_num=trial_num)

    async def _emit_trial_metrics(self, trial_start: float, status: str) -> None:
        await self._event_broadcaster.emit_trial_metrics(trial_start, status, self._best_trial, self._config)

    async def _broadcast_persistence_warning_once(self) -> None:
        await self._event_broadcaster.broadcast_persistence_warning_once()

    async def _update_pareto_front(self) -> None:
        try:
            assert self._study is not None
            pareto_trial_numbers = {t.number for t in self._study.best_trials}
            async with self._lock:
                for recorded in self._trials:
                    recorded.is_pareto_optimal = recorded.trial_id in pareto_trial_numbers
            self._pareto_front_size = len(pareto_trial_numbers)
        except (optuna.exceptions.OptunaError, RuntimeError, ValueError, TypeError) as e:
            logger.warning("[AutoTuner] Pareto front update failed: %s", e)

    async def _handle_trial_result(self, trial, trial_num: int, score, tps, p99_lat, trial_start, params) -> bool:
        """트라이얼 결과 처리. 가지치기된 경우 True 반환."""
        assert self._config is not None
        if self._config.objective != "pareto" and trial.should_prune():
            async with self._study_lock:
                assert self._study is not None
                self._study.tell(trial, state=optuna.trial.TrialState.PRUNED)
            t = TuningTrial(
                trial_id=trial_num,
                params=params,
                tps=tps,
                p99_latency=p99_lat,
                score=score,
                status="pruned",
                pruned=True,
            )
            async with self._lock:
                self._trials.append(t)
                self._best_score_history.append(self._best_trial.score if self._best_trial else 0)
            try:
                await storage.save_trial(t)
            except (OSError, RuntimeError, ValueError) as e:
                logger.warning("[AutoTuner] Failed to persist trial %d to storage: %s", trial_num, e)
                await self._broadcast_persistence_warning_once()
            await self._emit_trial_metrics(trial_start, "pruned")
            await self._broadcast(
                {
                    "type": "trial_complete",
                    "data": {"trial_id": trial_num, "score": score, "tps": tps, "p99_latency": p99_lat, "pruned": True},
                }
            )
            return True

        if self._config.objective == "pareto":
            async with self._study_lock:
                assert self._study is not None
                self._study.tell(trial, [tps, p99_lat])
            score = tps / (p99_lat + 1) * 100
        else:
            async with self._study_lock:
                assert self._study is not None
                self._study.tell(trial, score)

        t = TuningTrial(
            trial_id=trial_num, params=params, tps=tps, p99_latency=p99_lat, score=score, status="completed"
        )
        async with self._lock:
            self._trials.append(t)
            direction = self._direction
            if (
                self._best_trial is None
                or (direction == "maximize" and score > self._best_trial.score)
                or (direction == "minimize" and score < self._best_trial.score)
            ):
                self._best_trial = t
            self._best_score_history.append(self._best_trial.score if self._best_trial else score)
        try:
            await storage.save_trial(t)
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning("[AutoTuner] Failed to persist trial %d to storage: %s", trial_num, e)
            await self._broadcast_persistence_warning_once()
        await self._emit_trial_metrics(trial_start, "completed")
        if self._config.objective == "pareto":
            await self._update_pareto_front()
        await self._broadcast(
            {
                "type": "trial_complete",
                "data": {"trial_id": trial_num, "score": score, "tps": tps, "p99_latency": p99_lat, "pruned": False},
            }
        )
        return False

    async def _save_auto_benchmark(self) -> int | None:
        if self._best_trial is None or self._config is None:
            return None

        try:
            model_name = await asyncio.wait_for(resolve_model_name(self._vllm_endpoint), timeout=3.0)
        except (TimeoutError, httpx.HTTPError, ValueError):
            model_name = os.getenv("VLLM_MODEL", "qwen2-5-7b-instruct")

        benchmark = Benchmark(
            name=f"auto-tune-{time.strftime('%Y%m%d-%H%M%S')}",
            config=LoadTestConfig(
                endpoint=self._vllm_endpoint,
                model=model_name,
                total_requests=self._config.eval_requests,
                concurrency=self._config.eval_concurrency,
                rps=self._config.eval_rps,
                stream=True,
            ),
            result=LoadTestResult(
                total=self._config.eval_requests,
                total_requested=self._config.eval_requests,
                success=self._config.eval_requests,
                failed=0,
                latency=LatencyStats(mean=self._best_trial.p99_latency, p99=self._best_trial.p99_latency),
                tps=TpsStats(mean=self._best_trial.tps, total=self._best_trial.tps),
                tokens_per_sec=self._best_trial.tps,
            ),
        )
        saved = await storage.save_benchmark(benchmark)
        return saved.id

    async def _finalize_tuning(self, auto_benchmark: bool = False) -> int | None:
        """튜닝 완료 후 최적 파라미터 적용 및 완료 broadcast."""
        assert self._config is not None
        assert self._study is not None
        benchmark_id: int | None = None
        if self._best_trial:
            logger.info(f"[AutoTuner] 튜닝 완료. 최적 파라미터로 InferenceService 재설정: {self._best_trial.params}")
            await self._apply_params(self._best_trial.params)
            await self._wait_for_ready()
            if auto_benchmark:
                try:
                    benchmark_id = await self._save_auto_benchmark()
                    if benchmark_id is not None:
                        await self._broadcast(
                            {
                                "type": "benchmark_saved",
                                "data": {
                                    "benchmark_id": benchmark_id,
                                },
                            }
                        )
                    else:
                        await self._broadcast(
                            {
                                "type": "tuning_warning",
                                "data": {
                                    "message": "자동 벤치마크 저장 ID를 확인할 수 없습니다",
                                },
                            }
                        )
                except (OSError, RuntimeError, ValueError, TunerError) as e:
                    logger.warning("[AutoTuner] Auto benchmark save failed: %s", e)
                    await self._broadcast(
                        {
                            "type": "tuning_warning",
                            "data": {
                                "message": "자동 벤치마크 저장에 실패했습니다",
                            },
                        }
                    )
        await self._broadcast(
            {
                "type": "tuning_complete",
                "data": {
                    "best_params": self._best_trial.params if self._best_trial else {},
                    "total_trials": len(self._trials),
                },
            }
        )
        return benchmark_id

    async def stop(self) -> dict[str, Any]:
        pending_task: asyncio.Task[Any] | None = None
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

    def _suggest_params(self, trial, config: TuningConfig) -> dict[str, Any]:
        params: dict[str, Any] = {}

        params["max_num_seqs"] = trial.suggest_int(
            "max_num_seqs",
            config.max_num_seqs_range[0],
            config.max_num_seqs_range[1],
            step=32,
        )

        params["gpu_memory_utilization"] = trial.suggest_float(
            "gpu_memory_utilization",
            config.gpu_memory_utilization_range[0],
            config.gpu_memory_utilization_range[1],
        )

        _model_len_choices = [
            v for v in [2048, 4096, 8192] if config.max_model_len_range[0] <= v <= config.max_model_len_range[1]
        ]
        if not _model_len_choices:
            _mid = (config.max_model_len_range[0] + config.max_model_len_range[1]) // 2
            _model_len_choices = [_mid]

        params["max_model_len"] = trial.suggest_categorical(
            "max_model_len",
            _model_len_choices,
        )

        params["enable_chunked_prefill"] = trial.suggest_categorical("enable_chunked_prefill", [True, False])

        params["enable_enforce_eager"] = trial.suggest_categorical("enable_enforce_eager", [True, False])

        _step = 256
        _batched_low = max(config.max_num_batched_tokens_range[0], params["max_num_seqs"])
        _batched_low = math.ceil(_batched_low / _step) * _step
        _batched_high = max(config.max_num_batched_tokens_range[1], _batched_low)
        _batched_high = math.floor(_batched_high / _step) * _step
        if _batched_high < _batched_low:
            _batched_high = _batched_low
        params["max_num_batched_tokens"] = trial.suggest_int(
            "max_num_batched_tokens",
            _batched_low,
            _batched_high,
            step=256,
        )

        if config.block_size_options:
            params["block_size"] = trial.suggest_categorical("block_size", config.block_size_options)

        if config.include_swap_space:
            params["swap_space"] = trial.suggest_float(
                "swap_space",
                config.swap_space_range[0],
                config.swap_space_range[1],
            )

        return params

    def _params_to_args(self, params: dict[str, Any]) -> list[str]:
        return self._k8s_operator.params_to_args(params)

    async def _apply_params(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._k8s_operator.apply_params(params, self._k8s_lock)

    async def _rollback_to_snapshot(self, trial_num: int) -> bool:
        return await self._k8s_operator.rollback_to_snapshot(trial_num, self._k8s_lock)

    def _compute_trial_score(self, result: dict[str, Any], config: TuningConfig) -> float:
        """부하 테스트 결과에서 점수 계산."""
        tps = result.get("tps", {}).get("total", 0)
        p99_lat = result.get("latency", {}).get("p99", 9999)
        if config.objective == "tps":
            return tps
        if config.objective == "latency":
            return -p99_lat
        return tps / (p99_lat + 1) * 100

    async def _run_warmup_load(
        self,
        endpoint: str,
        model: str,
        config: TuningConfig,
        trial_id: int,
    ) -> None:
        """Warmup phase 실행."""
        await self._broadcast(
            {
                "type": "phase",
                "data": {"trial_id": trial_id, "phase": "warmup", "requests": config.warmup_requests},
            }
        )
        warmup_config = LoadTestConfig(
            endpoint=endpoint,
            model=model,
            total_requests=config.warmup_requests,
            concurrency=min(config.eval_concurrency, config.warmup_requests),
            rps=config.eval_rps,
            stream=True,
        )
        try:
            await self._load_engine.run(warmup_config)
            logger.info("[AutoTuner] Warmup completed (%d requests)", config.warmup_requests)
        except Exception as e:  # intentional: warmup non-critical
            logger.warning("[AutoTuner] Warmup failed (continuing): %s", e)

    async def _run_probe_load(
        self,
        endpoint: str,
        model: str,
        config: TuningConfig,
        trial,
        trial_id: int,
    ) -> tuple[float, float, float]:
        """Probe phase (fast + full) 실행."""
        fast_requests = max(1, int(config.eval_requests * config.eval_fast_fraction))
        fast_config = LoadTestConfig(
            endpoint=endpoint,
            model=model,
            total_requests=fast_requests,
            concurrency=config.eval_concurrency,
            rps=config.eval_rps,
            stream=True,
        )
        await self._broadcast(
            {
                "type": "phase",
                "data": {"trial_id": trial_id, "phase": "evaluating"},
            }
        )
        fast_result = await self._load_engine.run(fast_config)
        fast_score = self._compute_trial_score(fast_result, config)

        if trial is not None and config.objective != "pareto":
            trial.report(fast_score, step=0)
            if trial.should_prune():
                tps = fast_result.get("tps", {}).get("total", 0)
                p99_lat = fast_result.get("latency", {}).get("p99", 9999)
                return fast_score, tps, p99_lat

        remaining_requests = config.eval_requests - fast_requests
        if remaining_requests > 0:
            full_config = LoadTestConfig(
                endpoint=endpoint,
                model=model,
                total_requests=remaining_requests,
                concurrency=config.eval_concurrency,
                rps=config.eval_rps,
                stream=True,
            )
            full_result = await self._load_engine.run(full_config)
            score = self._compute_trial_score(full_result, config)
            tps = full_result.get("tps", {}).get("total", 0)
            p99_lat = full_result.get("latency", {}).get("p99", 9999)
        else:
            score = fast_score
            tps = fast_result.get("tps", {}).get("total", 0)
            p99_lat = fast_result.get("latency", {}).get("p99", 9999)

        return score, tps, p99_lat

    async def _evaluate(
        self,
        endpoint: str,
        config: TuningConfig,
        trial=None,
        trial_num: int = 0,
    ) -> tuple[float, float, float]:
        """부하 테스트 실행 후 점수 반환 (fast probe + full evaluation)"""
        try:
            model_name = await asyncio.wait_for(resolve_model_name(endpoint), timeout=3.0)
        except (TimeoutError, httpx.HTTPError, ValueError):
            model_name = os.getenv("VLLM_MODEL", "auto")
        if not model_name or model_name == "auto":
            raise ValueError(f"Cannot resolve model name from {endpoint}. Set VLLM_MODEL env var.")
        _trial_id = trial.number if trial is not None and hasattr(trial, "number") else trial_num

        if config.warmup_requests > 0:
            await self._run_warmup_load(endpoint, model_name, config, _trial_id)

        score, tps, p99_lat = await self._run_probe_load(endpoint, model_name, config, trial, _trial_id)

        return score, tps, p99_lat

    async def get_importance(self) -> dict[str, Any]:
        """파라미터 중요도 반환 (Optuna FAnova)"""
        if not self._study or len(self._trials) < 5:
            return {}
        # FAnova not supported for multi-objective
        try:
            if hasattr(self._study, "directions") and len(getattr(self._study, "directions", [])) > 1:
                return {}
        except optuna.exceptions.OptunaError as e:
            logger.warning("[AutoTuner] Multi-objective check failed: %s", e)
        try:
            importance = await asyncio.to_thread(optuna.importance.get_param_importances, self._study)
            return dict(importance)
        except (optuna.exceptions.OptunaError, RuntimeError, ValueError, TypeError) as e:
            logger.warning("[AutoTuner] get_importance failed: %s", e)
            return {}
