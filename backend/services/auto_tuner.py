"""
자동 파라미터 튜너 — Bayesian Optimization으로 최적 vLLM 설정 탐색
목표: 처리량(TPS) 최대화, 레이턴시(P99) 최소화
"""
import logging
import asyncio
import inspect
import os
import json
import datetime
import math
from .model_resolver import resolve_model_name
from typing import Optional, List
from kubernetes import client as k8s_client, config as k8s_config
from models.load_test import TuningConfig, TuningTrial, LoadTestConfig

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)
OPTUNA_AVAILABLE = True

# Prometheus metrics integration (optional)
try:
    from metrics.prometheus_metrics import (
        tuner_trials_total,
        tuner_best_score,
        tuner_trial_duration_seconds,
    )
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

K8S_NAMESPACE = os.getenv("K8S_NAMESPACE", "default")
K8S_DEPLOYMENT = os.getenv("K8S_DEPLOYMENT_NAME", "vllm-deployment")
K8S_CONFIGMAP = os.getenv("K8S_CONFIGMAP_NAME", "vllm-config")


class AutoTuner:
    def __init__(self, metrics_collector, load_engine):
        self._metrics = metrics_collector
        self._load_engine = load_engine
        self._trials: List[TuningTrial] = []
        self._best_trial: Optional[TuningTrial] = None
        self._running = False
        self._study = None
        self._config: Optional[TuningConfig] = None  # Set in start()
        self._k8s_available = False
        self._cm_snapshot: dict | None = None
        self._last_rollback_trial: int | None = None
        self._pareto_front_size: int | None = None
        # SSE broadcasting primitives
        self._subscribers: list[asyncio.Queue] = []
        self._subscribers_lock: asyncio.Lock = asyncio.Lock()
        self._lock = asyncio.Lock()
        self._study_lock = asyncio.Lock()
        self._k8s_lock = asyncio.Lock()
        self._wait_durations: list[float] = []
        self._total_wait_seconds: float = 0.0
        self._poll_count: int = 0
        self._best_score_history: list[float] = []
        self._init_k8s()

    def _init_k8s(self):
        try:
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()
            self._k8s_apps = k8s_client.AppsV1Api()
            self._k8s_core = k8s_client.CoreV1Api()
            self._k8s_custom = k8s_client.CustomObjectsApi()
            self._k8s_available = True
        except Exception as e:
            logger.warning("K8s client unavailable: %s", e)

    async def _wait_for_ready(self, timeout: int = 300, interval: int = 5) -> bool:
        """InferenceService가 준비될 때까지 폴링합니다."""
        import time as _time
        logger.info(f"[AutoTuner] InferenceService '{K8S_DEPLOYMENT}' 준비 대기 중...")
        wait_start = _time.monotonic()
        start_time = asyncio.get_event_loop().time()
        result = False
        while asyncio.get_event_loop().time() - start_time < timeout:
            self._poll_count += 1
            try:
                inferenceservice = await asyncio.to_thread(
                    self._k8s_custom.get_namespaced_custom_object,
                    group="serving.kserve.io",
                    version="v1beta1",
                    name=K8S_DEPLOYMENT,
                    namespace=K8S_NAMESPACE,
                    plural="inferenceservices",
                )

                if inspect.isawaitable(inferenceservice):
                    inferenceservice = await inferenceservice
                
                if inferenceservice and "status" in inferenceservice and "conditions" in inferenceservice["status"]:
                    for condition in inferenceservice["status"]["conditions"]:
                        if condition.get("type") == "Ready" and condition.get("status") == "True":
                            logger.info(f"[AutoTuner] InferenceService '{K8S_DEPLOYMENT}' 준비 완료.")
                            result = True
                            break
                if result:
                    break
            except Exception as e:
                logger.warning(f"[AutoTuner] InferenceService 상태 확인 중 오류 발생: {e}")
            
            await asyncio.sleep(interval)
        
        wait_duration = _time.monotonic() - wait_start
        self._wait_durations.append(round(wait_duration, 2))
        self._total_wait_seconds += wait_duration

        if not result:
            logger.error(f"[AutoTuner] InferenceService '{K8S_DEPLOYMENT}' 시간 초과: {timeout}초 내에 준비되지 않음.")
        return result

    async def subscribe(self) -> asyncio.Queue:
        """Subscribe to tuning events. Returns a queue that will receive events."""
        q: asyncio.Queue = asyncio.Queue()
        async with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue):
        """Unsubscribe from tuning events."""
        async with self._subscribers_lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    async def _broadcast(self, data: dict):
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
    def wait_metrics(self) -> dict:
        return {
            "total_wait_seconds": round(self._total_wait_seconds, 2),
            "poll_count": self._poll_count,
            "per_trial_waits": [round(d, 2) for d in self._wait_durations],
        }

    async def start(self, config: TuningConfig, vllm_endpoint: str) -> dict:
        async with self._lock:
            if self._running:
                return {"error": "이미 튜닝이 실행 중입니다."}
            if not OPTUNA_AVAILABLE:
                return {"error": "optuna 패키지가 필요합니다: pip install optuna"}
            self._running = True
            self._config = config
            self._trials = []
            self._best_score_history = []
            self._best_trial = None
            storage_url = os.getenv("OPTUNA_STORAGE_URL")  # e.g., "sqlite:////tmp/optuna.db"
            self._pareto_front_size = None
            direction = "maximize"
            if config.objective == "pareto":
                sampler = optuna.samplers.NSGAIISampler(seed=42)
                pruner = optuna.pruners.NopPruner()
                _study_name = "vllm-tuner-pareto"
                direction_kwarg = {"directions": ["maximize", "minimize"]}
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
                    self._study = await asyncio.to_thread(
                        optuna.create_study,
                        sampler=sampler,
                        pruner=pruner,
                        storage=storage,
                        study_name=_study_name,
                        load_if_exists=True,
                        **direction_kwarg,
                    )
                    logger.info("[AutoTuner] Using SQLite storage: %s (study: %s)", storage_url, _study_name)
                    # Warm-start: enqueue best trial from previous run
                    if self._study.best_trials:
                        best_params = self._study.best_trial.params
                        self._study.enqueue_trial(params=best_params)
                        logger.info("[AutoTuner] Warm-start: enqueued previous best params: %s", best_params)
                except Exception as e:
                    logger.warning("[AutoTuner] SQLite storage failed, falling back to in-memory: %s", e)
                    self._study = optuna.create_study(
                        sampler=sampler,
                        pruner=pruner,
                        **direction_kwarg,
                    )
            else:
                self._study = optuna.create_study(
                    sampler=sampler,
                    pruner=pruner,
                    **direction_kwarg,
                )

        try:
            for trial_num in range(config.n_trials):
                if not self._running:
                    break

                async with self._study_lock:
                    trial = self._study.ask()
                params = self._suggest_params(trial, config)
                # Start trial timer (emission will be non-fatal if metrics are unavailable)
                import time as _time
                _trial_start = _time.monotonic()

                # Broadcast trial start event immediately after parameters are decided
                await self._broadcast({
                    "type": "trial_start",
                    "data": {"trial_id": trial_num, "params": params},
                })

                # 파라미터 적용 (Kubernetes ConfigMap 업데이트)
                apply_result = await self._apply_params(params)
                if not apply_result["success"]:
                    async with self._study_lock:
                        self._study.tell(trial, state=optuna.trial.TrialState.FAIL)
                    continue

                # vLLM 재시작 대기
                ready = await self._wait_for_ready()
                if not ready:
                    logger.warning("[AutoTuner] Trial %d: InferenceService not ready, rolling back", trial_num)
                    await self._rollback_to_snapshot(trial_num)
                    async with self._study_lock:
                        self._study.tell(trial, state=optuna.trial.TrialState.FAIL)
                    continue

                # 성능 측정
                score, tps, p99_lat = await self._evaluate(vllm_endpoint, config, trial=trial)

                if config.objective != "pareto" and trial.should_prune():
                    async with self._study_lock:
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
                        current_best = self._best_trial.score if self._best_trial else 0
                        self._best_score_history.append(current_best)
                    # Emit metrics for pruned trial
                    try:
                        if _METRICS_AVAILABLE:
                            _trial_duration = _time.monotonic() - _trial_start
                            tuner_trial_duration_seconds.observe(_trial_duration)
                            tuner_trials_total.labels(status="pruned").inc()
                    except Exception as _e:
                        logger.debug("[AutoTuner] Metrics emit failed (non-critical): %s", _e)
                    await self._broadcast({
                        "type": "trial_complete",
                        "data": {
                            "trial_id": trial_num,
                            "score": score,
                            "tps": tps,
                            "p99_latency": p99_lat,
                            "pruned": True,
                        },
                    })
                    continue

                if config.objective == "pareto":
                    async with self._study_lock:
                        self._study.tell(trial, [tps, p99_lat])
                    score = tps / (p99_lat + 1) * 100  # balanced score for best_trial tracking
                else:
                    async with self._study_lock:
                        self._study.tell(trial, score)

                t = TuningTrial(
                    trial_id=trial_num,
                    params=params,
                    tps=tps,
                    p99_latency=p99_lat,
                    score=score,
                    status="completed",
                )
                async with self._lock:
                    self._trials.append(t)
                    if self._best_trial is None or (direction == "maximize" and score > self._best_trial.score) or (direction == "minimize" and score < self._best_trial.score):
                        self._best_trial = t
                    self._best_score_history.append(
                        self._best_trial.score if self._best_trial else score
                    )
                # Emit metrics for completed trial
                try:
                    if _METRICS_AVAILABLE:
                        _trial_duration = _time.monotonic() - _trial_start
                        tuner_trial_duration_seconds.observe(_trial_duration)
                        tuner_trials_total.labels(status="completed").inc()
                        if self._best_trial is not None:
                            tuner_best_score.labels(objective=config.objective).set(self._best_trial.score)
                except Exception as _e:
                    logger.debug("[AutoTuner] Metrics emit failed (non-critical): %s", _e)

                if config.objective == "pareto":
                    try:
                        pareto_trial_numbers = {t.number for t in self._study.best_trials}
                        async with self._lock:
                            for recorded in self._trials:
                                recorded.is_pareto_optimal = (recorded.trial_id in pareto_trial_numbers)
                        self._pareto_front_size = len(pareto_trial_numbers)
                    except Exception:
                        pass

                # Broadcast trial completion event
                await self._broadcast({
                    "type": "trial_complete",
                    "data": {
                        "trial_id": trial_num,
                        "score": score,
                        "tps": tps,
                        "p99_latency": p99_lat,
                        "pruned": False,
                    },
                })

            if self._best_trial:
                logger.info(f"[AutoTuner] 튜닝 완료. 최적 파라미터로 InferenceService 재설정: {self._best_trial.params}")
                await self._apply_params(self._best_trial.params, restart_only=True)
                await self._wait_for_ready()

            # Broadcast tuning completion after all trials finished
            await self._broadcast({
                "type": "tuning_complete",
                "data": {
                    "best_params": self._best_trial.params if self._best_trial else {},
                    "total_trials": len(self._trials),
                },
            })

            return {
                "completed": True,
                "best_params": self._best_trial.params if self._best_trial else {},
                "best_score": self._best_trial.score if self._best_trial else 0,
                "trials": len(self._trials),
            }
        finally:
            self._running = False

    async def stop(self):
        async with self._lock:
            self._running = False

    def _suggest_params(self, trial, config: TuningConfig) -> dict:
        params: dict[str, object] = {}

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

    async def _apply_params(self, params: dict, restart_only: bool = False) -> dict:
        """ConfigMap 업데이트 → Deployment 재시작"""
        if not self._k8s_available:
            logger.info(f"[AutoTuner] K8s 없음 — 파라미터 적용 시뮬레이션: {params}")
            return {"success": True}

        try:
            async with self._k8s_lock:
                if not restart_only:
                    # ConfigMap 업데이트
                    logger.info(f"[AutoTuner] ConfigMap '{K8S_CONFIGMAP}' in namespace '{K8S_NAMESPACE}'")
                    current_cm = await asyncio.to_thread(self._k8s_core.read_namespaced_config_map,
                                                         name=K8S_CONFIGMAP,
                                                         namespace=K8S_NAMESPACE)
                    self._cm_snapshot = dict(current_cm.data or {})
                    
                    config_data = {
                        "MAX_NUM_SEQS": str(params["max_num_seqs"]),
                        "GPU_MEMORY_UTILIZATION": str(
                            params["gpu_memory_utilization"]
                        ),
                        "MAX_MODEL_LEN": str(params["max_model_len"]),
                        "ENABLE_CHUNKED_PREFILL": str(
                            params["enable_chunked_prefill"]
                        ).lower(),
                    }

                    if "max_num_batched_tokens" in params:
                        config_data[
                            "MAX_NUM_BATCHED_TOKENS"
                        ] = str(params["max_num_batched_tokens"])
                    if "block_size" in params:
                        config_data["BLOCK_SIZE"] = str(params["block_size"])
                    if "swap_space" in params:
                        config_data["SWAP_SPACE"] = str(params["swap_space"])

                    patch_body = {"data": config_data}
                    
                    await asyncio.to_thread(self._k8s_core.patch_namespaced_config_map,
                                             name=K8S_CONFIGMAP,
                                             namespace=K8S_NAMESPACE,
                                             body=patch_body)
                    logger.info(f"[AutoTuner] ConfigMap '{K8S_CONFIGMAP}' patched successfully.")

                # InferenceService 재시작 트리거
                try:
                    k8s_custom_api = k8s_client.CustomObjectsApi()
                    group = "serving.kserve.io"
                    version = "v1beta1"
                    plural = "inferenceservices"
                    name = K8S_DEPLOYMENT # Use K8S_DEPLOYMENT for InferenceService name
                    
                    restart_body = {
                        "spec": {
                            "predictor": {
                                "annotations": {
                                    "serving.kserve.io/restartedAt": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
                                }
                            }
                        }
                    }
                    
                    await asyncio.to_thread(k8s_custom_api.patch_namespaced_custom_object,
                                             group=group,
                                             version=version,
                                             namespace=K8S_NAMESPACE,
                                             plural=plural,
                                             name=name,
                                             body=restart_body)
                    logger.info(f"[AutoTuner] InferenceService '{name}' in namespace '{K8S_NAMESPACE}' restarted successfully.")
                except Exception as e:
                    logger.error(f"[AutoTuner] InferenceService 재시작 실패: {e}")

            return {"success": True}
        except Exception as e:
            logger.error(f"[AutoTuner] 파라미터 적용 실패: {e}")
            return {"success": False, "error": str(e)}

    async def _rollback_to_snapshot(self, trial_num: int) -> bool:
        if not self._k8s_available or self._cm_snapshot is None:
            logger.warning("[AutoTuner] Rollback requested but no snapshot available (trial %d)", trial_num)
            return False
        try:
            async with self._k8s_lock:
                await asyncio.to_thread(
                    self._k8s_core.patch_namespaced_config_map,
                    name=K8S_CONFIGMAP,
                    namespace=K8S_NAMESPACE,
                    body={"data": self._cm_snapshot},
                )
                k8s_custom_api = k8s_client.CustomObjectsApi()
                restart_body = {
                    "spec": {
                        "predictor": {
                            "annotations": {
                                "serving.kserve.io/restartedAt": datetime.datetime.now(
                                    datetime.timezone.utc
                                ).isoformat().replace("+00:00", "Z")
                            }
                        }
                    }
                }
                await asyncio.to_thread(
                    k8s_custom_api.patch_namespaced_custom_object,
                    group="serving.kserve.io",
                    version="v1beta1",
                    namespace=K8S_NAMESPACE,
                    plural="inferenceservices",
                    name=K8S_DEPLOYMENT,
                    body=restart_body,
                )
            self._last_rollback_trial = trial_num
            logger.info("[AutoTuner] Rollback to snapshot completed for trial %d", trial_num)
            return True
        except Exception as e:
            logger.error("[AutoTuner] Rollback failed for trial %d: %s", trial_num, e)
            return False

    async def _evaluate(
        self,
        endpoint: str,
        config: TuningConfig,
        trial=None,
    ) -> tuple[float, float, float]:
        """부하 테스트 실행 후 점수 반환 (fast probe + full evaluation)"""
        model_name = await resolve_model_name(endpoint)

        if config.warmup_requests > 0:
            warmup_config = LoadTestConfig(
                endpoint=endpoint,
                model=model_name,
                total_requests=config.warmup_requests,
                concurrency=min(config.eval_concurrency, config.warmup_requests),
                rps=config.eval_rps,
                stream=True,
            )
            try:
                await self._load_engine.run(warmup_config)
                logger.info("[AutoTuner] Warmup completed (%d requests)", config.warmup_requests)
            except Exception as e:
                logger.warning("[AutoTuner] Warmup failed (continuing): %s", e)

        def _compute_score(result: dict) -> float:
            tps = result.get("tps", {}).get("total", 0)
            p99_lat = result.get("latency", {}).get("p99", 9999)
            if config.objective == "tps":
                return tps
            if config.objective == "latency":
                return -p99_lat
            return tps / (p99_lat + 1) * 100

        fast_requests = max(1, int(config.eval_requests * config.eval_fast_fraction))
        fast_config = LoadTestConfig(
            endpoint=endpoint,
            model=model_name,
            total_requests=fast_requests,
            concurrency=config.eval_concurrency,
            rps=config.eval_rps,
            stream=True,
        )
        fast_result = await self._load_engine.run(fast_config)
        fast_score = _compute_score(fast_result)

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
                model=model_name,
                total_requests=remaining_requests,
                concurrency=config.eval_concurrency,
                rps=config.eval_rps,
                stream=True,
            )
            full_result = await self._load_engine.run(full_config)
            score = _compute_score(full_result)
            tps = full_result.get("tps", {}).get("total", 0)
            p99_lat = full_result.get("latency", {}).get("p99", 9999)
        else:
            score = fast_score
            tps = fast_result.get("tps", {}).get("total", 0)
            p99_lat = fast_result.get("latency", {}).get("p99", 9999)

        return score, tps, p99_lat

    def get_importance(self) -> dict:
        """파라미터 중요도 반환 (Optuna FAnova)"""
        if not self._study or len(self._trials) < 5:
            return {}
        # FAnova not supported for multi-objective
        try:
            if hasattr(self._study, "directions") and len(getattr(self._study, "directions", [])) > 1:
                return {}
        except Exception:
            pass
        try:
            importance = optuna.importance.get_param_importances(self._study)
            return dict(importance)
        except Exception:
            return {}
