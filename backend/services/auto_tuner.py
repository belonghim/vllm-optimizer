"""
자동 파라미터 튜너 — Bayesian Optimization으로 최적 vLLM 설정 탐색
목표: 처리량(TPS) 최대화, 레이턴시(P99) 최소화
"""

import asyncio
import logging
import math
import os
import time
from contextlib import suppress
from typing import Any, cast

import optuna
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.exceptions import ApiException
from models.load_test import (  # pyright: ignore[reportImplicitRelativeImport]
    Benchmark,
    LatencyStats,
    LoadTestConfig,
    LoadTestResult,
    TpsStats,
    TuningConfig,
    TuningTrial,
)
from services.cr_adapter import CRAdapter, TUNING_ARG_PREFIXES, args_list_to_config_dict, get_cr_adapter  # pyright: ignore[reportImplicitRelativeImport]
from services.shared import runtime_config, storage  # pyright: ignore[reportImplicitRelativeImport]

from .model_resolver import resolve_model_name

optuna.logging.set_verbosity(optuna.logging.WARNING)
OPTUNA_AVAILABLE = True

# Prometheus metrics integration (optional)
_metrics_available: bool = False
tuner_trials_total: Any = None
tuner_best_score: Any = None
tuner_trial_duration_seconds: Any = None
try:
    from metrics.prometheus_metrics import (  # pyright: ignore[reportImplicitRelativeImport]
        tuner_best_score,  # type: ignore[assignment]
        tuner_trial_duration_seconds,  # type: ignore[assignment]
        tuner_trials_total,  # type: ignore[assignment]
    )

    _metrics_available = True
except ImportError:
    pass

logger = logging.getLogger(__name__)


def _get_k8s_namespace() -> str:
    namespace = runtime_config.vllm_namespace
    return namespace if namespace else "default"


def _get_vllm_is_name() -> str:
    return runtime_config.vllm_is_name or "small-llm-d"


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
        self._config: TuningConfig | None = None  # Set in start()
        self._k8s_available = False
        self._k8s_core: k8s_client.CoreV1Api | None = None
        self._is_args_snapshot: Any = None
        self._last_rollback_trial: int | None = None
        self._pareto_front_size: int | None = None
        # SSE broadcasting primitives
        self._subscribers: list[asyncio.Queue[Any]] = []
        self._subscribers_lock: asyncio.Lock = asyncio.Lock()
        self._lock = asyncio.Lock()
        self._study_lock = asyncio.Lock()
        self._k8s_lock = asyncio.Lock()
        self._wait_durations: list[float] = []
        self._total_wait_seconds: float = 0.0
        self._poll_count: int = 0
        self._cooldown_secs: int = 30
        self._best_score_history: list[float] = []
        self._persistence_warning_sent: bool = False
        self._current_task: asyncio.Task[Any] | None = None
        self._init_k8s()

    def _init_k8s(self) -> None:
        try:
            try:
                k8s_config.load_incluster_config()
            except k8s_config.ConfigException:
                k8s_config.load_kube_config()
            self._k8s_apps = k8s_client.AppsV1Api()
            self._k8s_custom = k8s_client.CustomObjectsApi()
            self._k8s_available = True
        except k8s_config.ConfigException as e:
            logger.warning("K8s client unavailable: %s", e)

    @property
    def _cr_adapter(self) -> CRAdapter:
        return get_cr_adapter()

    async def _wait_for_ready(self, timeout: int = 300, interval: int = 5) -> bool:
        namespace = _get_k8s_namespace()
        is_name = _get_vllm_is_name()
        logger.info(f"[AutoTuner] InferenceService '{is_name}' 준비 대기 중...")
        wait_start = time.monotonic()
        start_time = asyncio.get_event_loop().time()
        result = False
        while asyncio.get_event_loop().time() - start_time < timeout:
            if self._cancel_event.is_set():
                logger.info("[AutoTuner] 준비 대기가 취소되었습니다.")
                break

            self._poll_count += 1
            try:
                inferenceservice = await asyncio.to_thread(
                    self._k8s_custom.get_namespaced_custom_object,
                    group=self._cr_adapter.api_group(),
                    version=self._cr_adapter.api_version(),
                    name=is_name,
                    namespace=namespace,
                    plural=self._cr_adapter.api_plural(),
                )
                _isvc: dict[str, Any] = cast(dict[str, Any], inferenceservice) if inferenceservice else {}
                if self._cr_adapter.check_ready(_isvc.get("status", {})):
                    logger.info(f"[AutoTuner] InferenceService '{is_name}' 준비 완료.")
                    result = True
                    break
            except ApiException as e:
                if e.status == 403:
                    logger.error(f"[AutoTuner] IS 상태 확인 403 Forbidden: {e}. 즉시 중단.")
                    break
                logger.warning(f"[AutoTuner] IS 상태 확인 오류: {e}")

            try:
                await asyncio.wait_for(self._cancel_event.wait(), timeout=interval)
                logger.info("[AutoTuner] 준비 대기 중 취소 신호를 감지했습니다.")
                break
            except TimeoutError:
                await asyncio.sleep(0)

        wait_duration = time.monotonic() - wait_start
        self._wait_durations.append(round(wait_duration, 2))
        self._total_wait_seconds += wait_duration

        if not result and not self._cancel_event.is_set():
            logger.error(f"[AutoTuner] InferenceService '{is_name}' 시간 초과: {timeout}초.")

        if result and not self._cancel_event.is_set():
            cooldown = self._cooldown_secs
            logger.info(f"[AutoTuner] 메트릭 안정화를 위해 {cooldown}초 대기 중...")
            try:
                await asyncio.wait_for(self._cancel_event.wait(), timeout=cooldown)
                logger.info("[AutoTuner] 쿨다운 중 취소 신호를 감지했습니다.")
                return False
            except TimeoutError:
                pass

        return result

    async def _preflight_check(self) -> dict[str, Any]:
        if not self._k8s_available:
            return {
                "success": False,
                "error": "K8s 클라이언트를 초기화할 수 없습니다. 클러스터 연결을 확인하세요.",
                "error_type": "k8s_unavailable",
            }
        namespace = _get_k8s_namespace()
        is_name = _get_vllm_is_name()
        try:
            await asyncio.to_thread(
                self._k8s_custom.get_namespaced_custom_object,
                group=self._cr_adapter.api_group(),
                version=self._cr_adapter.api_version(),
                name=is_name,
                namespace=namespace,
                plural=self._cr_adapter.api_plural(),
            )
            return {"success": True}
        except ApiException as e:
            if e.status == 403:
                return {
                    "success": False,
                    "error": "InferenceService 접근 권한이 없습니다 (403 Forbidden). Role/RoleBinding 설정을 확인하세요.",
                    "error_type": "rbac",
                }
            if e.status == 404:
                return {
                    "success": False,
                    "error": f"InferenceService '{is_name}'을(를) '{namespace}'에서 찾을 수 없습니다.",
                    "error_type": "not_found",
                }
            return {
                "success": False,
                "error": f"K8s API 오류: {e}",
                "error_type": "k8s_error",
            }

    async def subscribe(self) -> asyncio.Queue[Any]:
        """Subscribe to tuning events. Returns a queue that will receive events."""
        q: asyncio.Queue[Any] = asyncio.Queue()
        async with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[Any]) -> None:
        """Unsubscribe from tuning events."""
        async with self._subscribers_lock:
            with suppress(ValueError):
                self._subscribers.remove(q)

    async def _broadcast(self, data: dict[str, Any]) -> None:
        """Broadcast an event to all subscribers."""
        async with self._subscribers_lock:
            targets = list(self._subscribers)
        for q in targets:
            await q.put(data)

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
        return {
            "total_wait_seconds": round(self._total_wait_seconds, 2),
            "poll_count": self._poll_count,
            "per_trial_waits": [round(d, 2) for d in self._wait_durations],
        }

    async def _init_tuning_state(self, config: TuningConfig) -> None:
        self._config = config
        self._trials = []
        self._best_score_history = []
        self._best_trial = None
        self._pareto_front_size = None
        self._persistence_warning_sent = False
        storage_url = os.getenv("OPTUNA_STORAGE_URL")
        self._direction, self._study = await self._setup_study(config, storage_url)

    async def start(
        self,
        config: TuningConfig,
        vllm_endpoint: str,
        auto_benchmark: bool = False,
        skip_preflight: bool = False,
    ) -> dict[str, Any]:
        state_initialized = False
        _running_row_id: int | None = None
        try:
            async with self._lock:
                if self._running:
                    return {"error": "이미 튜닝이 실행 중입니다."}
                if not OPTUNA_AVAILABLE:
                    return {"error": "optuna 패키지가 필요합니다: pip install optuna"}
                if self._cancel_event.is_set():
                    await asyncio.sleep(0.1)
                self._cancel_event.clear()
                self._running = True
                state_initialized = True
                try:
                    _running_row_id = await storage.set_running("tuner")
                except Exception as e:
                    logger.warning("[AutoTuner] Failed to record running state: %s", e)
                await self._init_tuning_state(config)

            self._vllm_endpoint = vllm_endpoint
            if not skip_preflight:
                logger.info("[AutoTuner] 튜닝 시작 전 K8s 권한 사전 검증 중...")
                preflight = await self._preflight_check()
                if not preflight["success"]:
                    error_msg = preflight.get("error", "Preflight 검증 실패")
                    error_type = preflight.get("error_type", "preflight_error")
                    await self._broadcast(
                        {
                            "type": "tuning_error",
                            "data": {"error": error_msg, "error_type": error_type},
                        }
                    )
                    return {"error": error_msg, "error_type": error_type}

            logger.info("[AutoTuner] 튜닝 시작 전 InferenceService 상태 확인 중...")
            if not await self._wait_for_ready(timeout=60, interval=5):
                if self._cancel_event.is_set():
                    return {"error": "튜닝이 취소되었습니다."}
                return {"error": "InferenceService가 준비되지 않았습니다. 튜닝을 시작할 수 없습니다."}

            for trial_num in range(config.n_trials):
                if self._cancel_event.is_set():
                    break
                if not self._running:
                    break

                async with self._study_lock:
                    assert self._study is not None
                    trial = self._study.ask()
                params = self._suggest_params(trial, config)
                _trial_start = time.monotonic()

                await self._broadcast(
                    {
                        "type": "trial_start",
                        "data": {"trial_id": trial_num, "params": params},
                    }
                )

                if not await self._apply_trial_params(trial, trial_num, params):
                    continue

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
                    continue

                try:
                    score, tps, p99_lat = await self._run_trial_evaluation(trial)
                except Exception as e:
                    logger.warning("[AutoTuner] Trial %d evaluation failed: %s", trial_num, e)
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
                    continue

                pruned = await self._handle_trial_result(trial, trial_num, score, tps, p99_lat, _trial_start, params)
                if pruned:
                    continue

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
                    except Exception as e:
                        logger.warning("[AutoTuner] Failed to clear running state: %s", e)

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
                study = optuna.create_study(sampler=sampler, pruner=pruner, **direction_kwarg)  # type: ignore[arg-type]
        else:
            study = optuna.create_study(sampler=sampler, pruner=pruner, **direction_kwarg)  # type: ignore[arg-type]

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

    async def _run_trial_evaluation(self, trial) -> tuple[Any, ...]:
        """트라이얼 성능 평가 실행. (score, tps, p99_lat) 반환."""
        assert self._config is not None
        return await self._evaluate(self._vllm_endpoint, self._config, trial=trial)

    async def _emit_trial_metrics(self, trial_start: float, status: str) -> None:
        try:
            if _metrics_available:
                tuner_trial_duration_seconds.observe(time.monotonic() - trial_start)
                tuner_trials_total.labels(status=status).inc()
                if status == "completed" and self._best_trial is not None:
                    assert self._config is not None
                    tuner_best_score.labels(objective=self._config.objective).set(self._best_trial.score)
        except Exception as _e:  # intentional: non-critical metrics
            logger.debug("[AutoTuner] Metrics emit failed (non-critical): %s", _e)

    async def _broadcast_persistence_warning_once(self) -> None:
        if self._persistence_warning_sent:
            return
        self._persistence_warning_sent = True
        await self._broadcast(
            {
                "type": "tuning_warning",
                "data": {
                    "message": "트라이얼 저장에 실패했지만 튜닝은 계속 진행합니다",
                },
            }
        )

    async def _update_pareto_front(self) -> None:
        try:
            assert self._study is not None
            pareto_trial_numbers = {t.number for t in self._study.best_trials}
            async with self._lock:
                for recorded in self._trials:
                    recorded.is_pareto_optimal = recorded.trial_id in pareto_trial_numbers
            self._pareto_front_size = len(pareto_trial_numbers)
        except Exception as e:  # intentional: non-critical
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
            except Exception as e:
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
        except Exception as e:
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
        except Exception:
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
                except Exception as e:
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
            except Exception as exc:
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
        """Convert tuning params to vLLM command-line args list."""
        args: list[str] = []

        # max_num_seqs
        if "max_num_seqs" in params:
            args.append(f"--max-num-seqs={params['max_num_seqs']}")

        # gpu_memory_utilization
        if "gpu_memory_utilization" in params:
            args.append(f"--gpu-memory-utilization={params['gpu_memory_utilization']}")

        # max_model_len
        if "max_model_len" in params:
            args.append(f"--max-model-len={params['max_model_len']}")

        # max_num_batched_tokens
        if "max_num_batched_tokens" in params:
            args.append(f"--max-num-batched-tokens={params['max_num_batched_tokens']}")

        # block_size (optional)
        if "block_size" in params:
            args.append(f"--block-size={params['block_size']}")

        # swap_space (optional)
        if "swap_space" in params:
            args.append(f"--swap-space={params['swap_space']}")

        # enable_chunked_prefill (bool)
        if params.get("enable_chunked_prefill"):
            args.append("--enable-chunked-prefill")

        # enable_enforce_eager (bool)
        if params.get("enable_enforce_eager"):
            args.append("--enforce-eager")

        return args

    async def _apply_params(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self._k8s_available:
            logger.error("[AutoTuner] K8s 클라이언트가 초기화되지 않아 파라미터를 적용할 수 없습니다.")
            return {
                "success": False,
                "error": "K8s 클라이언트가 초기화되지 않았습니다.",
                "error_type": "k8s_unavailable",
            }

        try:
            async with self._k8s_lock:
                namespace = _get_k8s_namespace()
                is_name = _get_vllm_is_name()
                logger.info(f"[AutoTuner] InferenceService '{is_name}' in namespace '{namespace}'")
                isvc = await asyncio.to_thread(
                    self._k8s_custom.get_namespaced_custom_object,
                    group=self._cr_adapter.api_group(),
                    version=self._cr_adapter.api_version(),
                    name=is_name,
                    namespace=namespace,
                    plural=self._cr_adapter.api_plural(),
                )
                _isvc2: dict[str, Any] = cast(dict[str, Any], isvc) if isvc else {}
                self._is_args_snapshot = self._cr_adapter.snapshot_args(_isvc2.get("spec", {}))

                tuning_args = self._params_to_args(params)
                params_config_dict = args_list_to_config_dict(tuning_args)
                patch_body = self._cr_adapter.build_args_patch(_isvc2.get("spec", {}), params_config_dict)

                await asyncio.to_thread(
                    self._k8s_custom.patch_namespaced_custom_object,
                    group=self._cr_adapter.api_group(),
                    version=self._cr_adapter.api_version(),
                    namespace=namespace,
                    plural=self._cr_adapter.api_plural(),
                    name=is_name,
                    body=patch_body,
                )
                logger.info(f"[AutoTuner] InferenceService '{is_name}' args patched successfully: {tuning_args}")

            return {"success": True}
        except ApiException as e:
            logger.error(f"[AutoTuner] InferenceService args patch failed: {e}")
            if e.status == 403:
                return {
                    "success": False,
                    "error": "InferenceService 패치 권한 없음 (403 Forbidden)",
                    "error_type": "rbac",
                }
            if e.status == 404:
                namespace = _get_k8s_namespace()
                is_name = _get_vllm_is_name()
                return {
                    "success": False,
                    "error": f"InferenceService '{is_name}'을(를) '{namespace}'에서 찾을 수 없습니다.",
                    "error_type": "not_found",
                }
            return {"success": False, "error": f"InferenceService args patch failed: {e}"}
        except Exception as e:  # intentional: K8s operation fallback
            logger.error(f"[AutoTuner] 파라미터 적용 실패: {e}")
            return {"success": False, "error": str(e)}

    async def _rollback_to_snapshot(self, trial_num: int) -> bool:
        if not self._k8s_available or self._is_args_snapshot is None:
            logger.warning("[AutoTuner] Rollback requested but no snapshot available (trial %d)", trial_num)
            return False
        try:
            async with self._k8s_lock:
                namespace = _get_k8s_namespace()
                is_name = _get_vllm_is_name()
                # Restore args from snapshot
                patch_body = self._cr_adapter.build_rollback_patch(self._is_args_snapshot)
                await asyncio.to_thread(
                    self._k8s_custom.patch_namespaced_custom_object,
                    group=self._cr_adapter.api_group(),
                    version=self._cr_adapter.api_version(),
                    namespace=namespace,
                    plural=self._cr_adapter.api_plural(),
                    name=is_name,
                    body=patch_body,
                )
                # No annotation needed — args change triggers automatic restart
            self._last_rollback_trial = trial_num
            logger.info("[AutoTuner] Rollback to snapshot completed for trial %d", trial_num)
            return True
        except ApiException as e:
            logger.error("[AutoTuner] Rollback failed for trial %d: %s", trial_num, e)
            return False

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
        except TimeoutError:
            model_name = os.getenv("VLLM_MODEL", "auto")
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
        except Exception as e:
            logger.warning("[AutoTuner] get_importance failed: %s", e)
            return {}
