"""
자동 파라미터 튜너 — Bayesian Optimization으로 최적 vLLM 설정 탐색
목표: 처리량(TPS) 최대화, 레이턴시(P99) 최소화
"""
import logging
import asyncio
import os
import time
import math
from .model_resolver import resolve_model_name
from typing import Optional, List, Any, cast
from kubernetes import client as k8s_client, config as k8s_config
from kubernetes.client.exceptions import ApiException
from models.load_test import TuningConfig, TuningTrial, LoadTestConfig  # pyright: ignore[reportImplicitRelativeImport]

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)
OPTUNA_AVAILABLE = True

# Prometheus metrics integration (optional)
_metrics_available: bool = False
tuner_trials_total: Any = None
tuner_best_score: Any = None
tuner_trial_duration_seconds: Any = None
try:
    from metrics.prometheus_metrics import (  # pyright: ignore[reportImplicitRelativeImport]
        tuner_trials_total,  # type: ignore[assignment]
        tuner_best_score,  # type: ignore[assignment]
        tuner_trial_duration_seconds,  # type: ignore[assignment]
    )
    _metrics_available = True
except ImportError:
    pass

logger = logging.getLogger(__name__)

K8S_NAMESPACE = os.getenv("K8S_NAMESPACE", "default")
K8S_DEPLOYMENT = os.getenv("K8S_DEPLOYMENT_NAME", "vllm-deployment")
VLLM_IS_NAME = os.getenv("VLLM_DEPLOYMENT_NAME") or "llm-ov"

# Tuning parameter prefixes for arg filtering (static args preserved)
TUNING_ARG_PREFIXES = (
    "--max-num-seqs",
    "--gpu-memory-utilization",
    "--max-model-len",
    "--max-num-batched-tokens",
    "--block-size",
    "--swap-space",
    "--enable-chunked-prefill",
    "--enforce-eager",
)


class AutoTuner:
    def __init__(self, metrics_collector, load_engine) -> None:
        self._metrics = metrics_collector
        self._load_engine = load_engine
        self._trials: List[TuningTrial] = []
        self._best_trial: Optional[TuningTrial] = None
        self._running = False
        self._study: Optional[optuna.Study] = None
        self._direction: str = "maximize"
        self._vllm_endpoint: str = ""
        self._config: Optional[TuningConfig] = None  # Set in start()
        self._k8s_available = False
        self._k8s_core: Optional[k8s_client.CoreV1Api] = None
        self._is_args_snapshot: list[str] | None = None
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
        self._best_score_history: list[float] = []
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

    async def _wait_for_ready(self, timeout: int = 300, interval: int = 5) -> bool:
        logger.info(f"[AutoTuner] InferenceService '{VLLM_IS_NAME}' 준비 대기 중...")
        wait_start = time.monotonic()
        start_time = asyncio.get_event_loop().time()
        result = False
        while asyncio.get_event_loop().time() - start_time < timeout:
            self._poll_count += 1
            try:
                inferenceservice = await asyncio.to_thread(
                    self._k8s_custom.get_namespaced_custom_object,
                    group="serving.kserve.io",
                    version="v1beta1",
                    name=VLLM_IS_NAME,
                    namespace=K8S_NAMESPACE,
                    plural="inferenceservices",
                )
                _isvc: dict[str, Any] = cast(dict[str, Any], inferenceservice) if inferenceservice else {}
                conditions = _isvc.get("status", {}).get("conditions", [])
                for c in conditions:
                    if c.get("type") == "Ready" and c.get("status") == "True":
                        logger.info(f"[AutoTuner] InferenceService '{VLLM_IS_NAME}' 준비 완료.")
                        result = True
                        break
                if result:
                    break
            except ApiException as e:
                logger.warning(f"[AutoTuner] IS 상태 확인 오류: {e}")

            await asyncio.sleep(interval)

        wait_duration = time.monotonic() - wait_start
        self._wait_durations.append(round(wait_duration, 2))
        self._total_wait_seconds += wait_duration

        if not result:
            logger.error(f"[AutoTuner] InferenceService '{VLLM_IS_NAME}' 시간 초과: {timeout}초.")
        return result

    async def subscribe(self) -> asyncio.Queue[Any]:
        """Subscribe to tuning events. Returns a queue that will receive events."""
        q: asyncio.Queue[Any] = asyncio.Queue()
        async with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[Any]) -> None:
        """Unsubscribe from tuning events."""
        async with self._subscribers_lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    async def _broadcast(self, data: dict[str, Any]) -> None:
        """Broadcast an event to all subscribers."""
        async with self._subscribers_lock:
            targets = list(self._subscribers)
        for q in targets:
            await q.put(data)

    @property
    def trials(self) -> List[TuningTrial]:
        return self._trials

    @property
    def best(self) -> Optional[TuningTrial]:
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
        self._running = True
        self._config = config
        self._trials = []
        self._best_score_history = []
        self._best_trial = None
        self._pareto_front_size = None
        storage_url = os.getenv("OPTUNA_STORAGE_URL")
        self._direction, self._study = await self._setup_study(config, storage_url)

    async def start(self, config: TuningConfig, vllm_endpoint: str) -> dict[str, Any]:
        async with self._lock:
            if self._running:
                return {"error": "이미 튜닝이 실행 중입니다."}
            if not OPTUNA_AVAILABLE:
                return {"error": "optuna 패키지가 필요합니다: pip install optuna"}
            await self._init_tuning_state(config)

        self._vllm_endpoint = vllm_endpoint
        try:
            for trial_num in range(config.n_trials):
                if not self._running:
                    break

                async with self._study_lock:
                    assert self._study is not None
                    trial = self._study.ask()
                params = self._suggest_params(trial, config)
                _trial_start = time.monotonic()

                await self._broadcast({
                    "type": "trial_start",
                    "data": {"trial_id": trial_num, "params": params},
                })

                if not await self._apply_trial_params(trial, trial_num, params):
                    continue

                await self._broadcast({
                    "type": "phase",
                    "data": {"trial_id": trial_num, "phase": "restarting"},
                })
                await self._broadcast({
                    "type": "phase",
                    "data": {"trial_id": trial_num, "phase": "waiting_ready"},
                })

                if not await self._wait_for_isvc_ready(trial, trial_num):
                    continue

                score, tps, p99_lat = await self._run_trial_evaluation(trial)

                pruned = await self._handle_trial_result(
                    trial, trial_num, score, tps, p99_lat, _trial_start, params
                )
                if pruned:
                    continue

            await self._finalize_tuning()

            return {
                "completed": True,
                "best_params": self._best_trial.params if self._best_trial else {},
                "best_score": self._best_trial.score if self._best_trial else 0,
                "trials": len(self._trials),
            }
        finally:
            self._running = False

    async def _setup_study(
        self, config: TuningConfig, storage_url: str | None
    ) -> tuple[str, optuna.Study]:
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
                study = optuna.create_study(
                    sampler=sampler, pruner=pruner, **direction_kwarg
                )  # type: ignore[arg-type]
        else:
            study = optuna.create_study(
                sampler=sampler, pruner=pruner, **direction_kwarg
            )  # type: ignore[arg-type]

        return direction, study

    async def _apply_trial_params(self, trial, trial_num: int, params: dict[str, Any]) -> bool:
        """InferenceService args 업데이트. 실패 시 Optuna FAIL 처리 후 False 반환."""
        await self._broadcast({
            "type": "phase",
            "data": {"trial_id": trial_num, "phase": "applying_config"},
        })
        apply_result = await self._apply_params(params)
        if not apply_result["success"]:
            async with self._study_lock:
                assert self._study is not None
                self._study.tell(trial, state=optuna.trial.TrialState.FAIL)
            return False
        return True

    async def _wait_for_isvc_ready(self, trial, trial_num: int) -> bool:
        """IS 준비 대기. 실패 시 rollback 및 Optuna FAIL 처리 후 False 반환."""
        ready = await self._wait_for_ready()
        if not ready:
            logger.warning("[AutoTuner] Trial %d: InferenceService not ready, rolling back", trial_num)
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

    async def _update_pareto_front(self) -> None:
        try:
            assert self._study is not None
            pareto_trial_numbers = {t.number for t in self._study.best_trials}
            async with self._lock:
                for recorded in self._trials:
                    recorded.is_pareto_optimal = (recorded.trial_id in pareto_trial_numbers)
            self._pareto_front_size = len(pareto_trial_numbers)
        except Exception as e:  # intentional: non-critical
            logger.debug("[AutoTuner] Pareto front update failed: %s", e)

    async def _handle_trial_result(
        self, trial, trial_num: int, score, tps, p99_lat, trial_start, params
    ) -> bool:
        """트라이얼 결과 처리. 가지치기된 경우 True 반환."""
        assert self._config is not None
        if self._config.objective != "pareto" and trial.should_prune():
            async with self._study_lock:
                assert self._study is not None
                self._study.tell(trial, state=optuna.trial.TrialState.PRUNED)
            t = TuningTrial(trial_id=trial_num, params=params, tps=tps,
                            p99_latency=p99_lat, score=score, status="pruned", pruned=True)
            async with self._lock:
                self._trials.append(t)
                self._best_score_history.append(self._best_trial.score if self._best_trial else 0)
            await self._emit_trial_metrics(trial_start, "pruned")
            await self._broadcast({"type": "trial_complete", "data": {
                "trial_id": trial_num, "score": score, "tps": tps,
                "p99_latency": p99_lat, "pruned": True}})
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

        t = TuningTrial(trial_id=trial_num, params=params, tps=tps,
                        p99_latency=p99_lat, score=score, status="completed")
        async with self._lock:
            self._trials.append(t)
            direction = self._direction
            if self._best_trial is None or \
               (direction == "maximize" and score > self._best_trial.score) or \
               (direction == "minimize" and score < self._best_trial.score):
                self._best_trial = t
            self._best_score_history.append(self._best_trial.score if self._best_trial else score)
        await self._emit_trial_metrics(trial_start, "completed")
        if self._config.objective == "pareto":
            await self._update_pareto_front()
        await self._broadcast({"type": "trial_complete", "data": {
            "trial_id": trial_num, "score": score, "tps": tps,
            "p99_latency": p99_lat, "pruned": False}})
        return False

    async def _finalize_tuning(self) -> None:
        """튜닝 완료 후 최적 파라미터 적용 및 완료 broadcast."""
        assert self._config is not None
        assert self._study is not None
        if self._best_trial:
            logger.info(
                f"[AutoTuner] 튜닝 완료. 최적 파라미터로 InferenceService 재설정: {self._best_trial.params}"
            )
            await self._apply_params(self._best_trial.params)
            await self._wait_for_ready()
        await self._broadcast({
            "type": "tuning_complete",
            "data": {
                "best_params": self._best_trial.params if self._best_trial else {},
                "total_trials": len(self._trials),
            },
        })

    async def stop(self) -> None:
        async with self._lock:
            self._running = False

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
            v for v in [2048, 4096, 8192]
            if config.max_model_len_range[0] <= v <= config.max_model_len_range[1]
        ]
        if not _model_len_choices:
            _mid = (
                config.max_model_len_range[0] + config.max_model_len_range[1]
            ) // 2
            _model_len_choices = [_mid]

        params["max_model_len"] = trial.suggest_categorical(
            "max_model_len",
            _model_len_choices,
        )

        params["enable_chunked_prefill"] = trial.suggest_categorical(
            "enable_chunked_prefill", [True, False]
        )

        params["enable_enforce_eager"] = trial.suggest_categorical(
            "enable_enforce_eager", [True, False]
        )

        _step = 256
        _batched_low = max(
            config.max_num_batched_tokens_range[0], params["max_num_seqs"]
        )
        _batched_low = math.ceil(_batched_low / _step) * _step
        _batched_high = max(
            config.max_num_batched_tokens_range[1], _batched_low
        )
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
            params["block_size"] = trial.suggest_categorical(
                "block_size", config.block_size_options
            )

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
            logger.info(f"[AutoTuner] K8s 없음 — 파라미터 적용 시뮬레이션: {params}")
            return {"success": True}

        try:
            async with self._k8s_lock:
                logger.info(f"[AutoTuner] InferenceService '{VLLM_IS_NAME}' in namespace '{K8S_NAMESPACE}'")
                isvc = await asyncio.to_thread(
                    self._k8s_custom.get_namespaced_custom_object,
                    group="serving.kserve.io",
                    version="v1beta1",
                    name=VLLM_IS_NAME,
                    namespace=K8S_NAMESPACE,
                    plural="inferenceservices",
                )
                _isvc2: dict[str, Any] = cast(dict[str, Any], isvc) if isvc else {}
                current_args = (
                    _isvc2.get("spec", {}).get("predictor", {}).get("model", {}).get("args") or []
                )
                self._is_args_snapshot = list(current_args)

                tuning_args = self._params_to_args(params)

                static_args = [
                    arg for arg in self._is_args_snapshot
                    if not any(arg.startswith(prefix) for prefix in TUNING_ARG_PREFIXES)
                ]

                new_args = static_args + tuning_args

                patch_body = {
                    "spec": {
                        "predictor": {
                            "model": {
                                "args": new_args
                            }
                        }
                    }
                }
                await asyncio.to_thread(
                    self._k8s_custom.patch_namespaced_custom_object,
                    group="serving.kserve.io",
                    version="v1beta1",
                    namespace=K8S_NAMESPACE,
                    plural="inferenceservices",
                    name=VLLM_IS_NAME,
                    body=patch_body,
                )
                logger.info(f"[AutoTuner] InferenceService '{VLLM_IS_NAME}' args patched successfully: {tuning_args}")

            return {"success": True}
        except ApiException as e:
            logger.error(f"[AutoTuner] InferenceService args patch failed: {e}")
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
                # Restore args from snapshot
                patch_body = {
                    "spec": {
                        "predictor": {
                            "model": {
                                "args": self._is_args_snapshot
                            }
                        }
                    }
                }
                await asyncio.to_thread(
                    self._k8s_custom.patch_namespaced_custom_object,
                    group="serving.kserve.io",
                    version="v1beta1",
                    namespace=K8S_NAMESPACE,
                    plural="inferenceservices",
                    name=VLLM_IS_NAME,
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
        await self._broadcast({
            "type": "phase",
            "data": {"trial_id": trial_id, "phase": "warmup", "requests": config.warmup_requests},
        })
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
        await self._broadcast({
            "type": "phase",
            "data": {"trial_id": trial_id, "phase": "evaluating"},
        })
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
        model_name = await resolve_model_name(endpoint)
        _trial_id = trial.number if trial is not None and hasattr(trial, "number") else trial_num

        if config.warmup_requests > 0:
            await self._run_warmup_load(endpoint, model_name, config, _trial_id)

        score, tps, p99_lat = await self._run_probe_load(
            endpoint, model_name, config, trial, _trial_id
        )

        return score, tps, p99_lat

    def get_importance(self) -> dict[str, Any]:
        """파라미터 중요도 반환 (Optuna FAnova)"""
        if not self._study or len(self._trials) < 5:
            return {}
        # FAnova not supported for multi-objective
        try:
            if hasattr(self._study, "directions") and len(getattr(self._study, "directions", [])) > 1:
                return {}
        except optuna.exceptions.OptunaError as e:
            logger.debug("[AutoTuner] Multi-objective check failed: %s", e)
        try:
            importance = optuna.importance.get_param_importances(self._study)
            return dict(importance)
        except optuna.exceptions.OptunaError:
            return {}
