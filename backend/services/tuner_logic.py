import asyncio
import hashlib
import json
import logging
import math
import time
from typing import Any, Protocol

import httpx
import optuna
from errors import TunerError  # pyright: ignore[reportImplicitRelativeImport]  # backend/ added to sys.path at runtime
from models.load_test import (  # pyright: ignore[reportImplicitRelativeImport]  # backend/ added to sys.path at runtime
    Benchmark,
    LatencyStats,
    LoadTestConfig,
    LoadTestResult,
    TpsStats,
    TuningConfig,
    TuningTrial,
)
from services.boot_diagnosis import first_violated_limit
from services.load_engine import (
    LoadTestEngine,  # pyright: ignore[reportImplicitRelativeImport]  # backend/ added to sys.path at runtime
)

from .model_resolver import resolve_model_name

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger = logging.getLogger(__name__)


def study_name_for(config: TuningConfig) -> str:
    """Persistent study name scoped to the tuned CR and its search space.

    Warm-starting from another model's best params or another SLA's scores is meaningless — so each
    target/space/SLA gets its own.
    """
    space = json.dumps(
        [
            config.target_key,
            config.max_num_seqs_range,
            config.gpu_memory_utilization_range,
            config.max_num_batched_tokens_range,
            config.max_model_len,
            config.eval_concurrency,
            config.p99_latency_sla_ms,
            config.max_tokens,
        ],
        default=str,
    )
    return f"vllm-tuner-{hashlib.sha1(space.encode()).hexdigest()[:12]}"


def kv_cache_oom_risk(params: dict[str, Any], config: TuningConfig) -> bool:
    """Return True when vLLM would refuse to start for lack of KV memory.

    Startup needs one max_model_len sequence of attention KV and, separately, the linear-attention
    (GDN/Mamba) state block for every max_num_seqs slot; both are checked against the same pool, not summed
    (verified on CUDA: 262144-token KV + 500 slots boots in a pool smaller than their sum). Attention KV beyond
    one sequence only causes preemption. Returns False when unknown.
    """
    if not (config.model_kv_bytes_per_token and config.memory_budget_gib):
        return False
    max_model_len = params.get("max_model_len", config.max_model_len)
    max_num_seqs = params.get("max_num_seqs", 256)
    gpu_util = params.get("gpu_memory_utilization", 0.9)
    window = max_model_len
    if config.model_sliding_window:
        # Sliding layers hold window-1 tokens plus the tokens of the step being scheduled.
        batched = params.get("max_num_batched_tokens") or config.max_num_batched_tokens_range[0]
        window = min(max_model_len, config.model_sliding_window - 1 + batched)
    required = max(
        config.model_kv_bytes_per_token * max_model_len + config.model_sliding_kv_bytes_per_token * window,
        config.model_linear_state_bytes_per_seq * max_num_seqs,
    )
    if config.memory_budget_dedicated_kv:
        available = config.memory_budget_gib * (1024**3)
    else:
        reserved = (config.model_weight_gib or 0.0) + config.memory_overhead_gib
        available = (config.memory_budget_gib * gpu_util - reserved) * (1024**3)
    return required > available * 0.9


class _Broadcaster(Protocol):
    async def broadcast(self, data: dict[str, Any]) -> None: ...


class TunerLogic:
    def __init__(self, load_engine: LoadTestEngine) -> None:
        self._load_engine = load_engine

    async def setup_study(
        self,
        config: TuningConfig,
        storage_url: str | None,
        broadcaster: _Broadcaster | None = None,
    ) -> tuple[str, optuna.Study]:
        direction = "maximize"
        sampler = optuna.samplers.TPESampler(seed=42)
        pruner = optuna.pruners.MedianPruner(n_startup_trials=3, n_warmup_steps=0)
        _study_name = study_name_for(config)

        if storage_url:
            try:
                storage = await asyncio.to_thread(
                    optuna.storages.RDBStorage,
                    storage_url,
                    engine_kwargs={"connect_args": {"check_same_thread": False}},
                )
                # Deleting persisted history is safe only because AutoTuner.start rejects
                # concurrent sessions; without it MedianPruner would prune this session's
                # early trials against another session's stale medians.
                try:
                    study_id = await asyncio.to_thread(storage.get_study_id_from_name, _study_name)
                    await asyncio.to_thread(storage.delete_study, study_id)
                    logger.info("[AutoTuner] Deleted stale study %s for fresh session", _study_name)
                except KeyError:
                    pass  # first session for this study name
                study = await asyncio.to_thread(  # type: ignore[arg-type]  # optuna.create_study returns Study|None, pyright can't track through to_thread
                    optuna.create_study,
                    sampler=sampler,
                    pruner=pruner,
                    storage=storage,
                    study_name=_study_name,
                    load_if_exists=True,
                    direction=direction,
                )
                logger.info("[AutoTuner] Using SQLite storage: %s (study: %s)", storage_url, _study_name)
                if study.best_trials:
                    best_params = study.best_trial.params
                    study.enqueue_trial(params=best_params)
                    logger.info("[AutoTuner] Warm-start: enqueued previous best params: %s", best_params)
            except Exception as e:  # intentional: storage fallback (SQLAlchemy/Optuna errors too diverse)
                logger.warning("[AutoTuner] SQLite storage failed, falling back to in-memory: %s", e)
                if broadcaster is not None:
                    await broadcaster.broadcast(
                        {
                            "type": "tuning_warning",
                            "data": {
                                "message": "스토리지 초기화 실패, 인메모리 모드로 실행합니다",
                            },
                        }
                    )
                try:
                    study = optuna.create_study(sampler=sampler, pruner=pruner, direction=direction)
                except optuna.exceptions.OptunaError as e:
                    raise TunerError(
                        "Optuna study initialization failed after storage fallback",
                        detail={"storage_url": storage_url},
                    ) from e
        else:
            try:
                study = optuna.create_study(sampler=sampler, pruner=pruner, direction=direction)
            except optuna.exceptions.OptunaError as e:
                raise TunerError(
                    "Optuna study initialization failed",
                    detail={"storage_url": storage_url},
                ) from e

        return direction, study

    def suggest_params(self, trial: optuna.trial.Trial, config: TuningConfig) -> dict[str, Any]:
        params: dict[str, Any] = {}

        params["max_num_seqs"] = trial.suggest_int(
            "max_num_seqs",
            config.max_num_seqs_range[0],
            config.max_num_seqs_range[1],
            step=32,
        )

        _gpu_util_low = config.gpu_memory_utilization_range[0]
        if (
            config.model_weight_gib
            and config.memory_budget_gib
            and config.memory_budget_gib > 0
            and not config.memory_budget_dedicated_kv
        ):
            _weight_fraction = (config.model_weight_gib * 1.1 + config.memory_overhead_gib) / config.memory_budget_gib
            _floor = math.ceil(_weight_fraction * 100) / 100
            _floor = min(_floor, config.gpu_memory_utilization_range[1] - 0.05)
            _gpu_util_low = max(_gpu_util_low, _floor)

        params["gpu_memory_utilization"] = trial.suggest_float(
            "gpu_memory_utilization",
            _gpu_util_low,
            config.gpu_memory_utilization_range[1],
        )

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

        params["max_model_len"] = config.max_model_len
        return params

    def compute_trial_score(self, result: dict[str, Any], config: TuningConfig) -> float:
        """TPS when p99 meets the SLA; otherwise negative, closer to 0 the smaller the violation."""
        tps = result.get("tps", {}).get("total", 0)
        p99_ms = result.get("latency", {}).get("p99", 9999) * 1000
        if p99_ms > config.p99_latency_sla_ms:
            return -(p99_ms / config.p99_latency_sla_ms)
        return tps

    async def run_warmup_load(
        self,
        endpoint: str,
        model: str,
        config: TuningConfig,
        trial_id: int,
        broadcaster: _Broadcaster | None = None,
    ) -> None:
        if broadcaster is not None:
            await broadcaster.broadcast(
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
            max_tokens=config.max_tokens,
            stream=True,
        )
        try:
            await self._load_engine.run(warmup_config)
            logger.info("[AutoTuner] Warmup completed (%d requests)", config.warmup_requests)
        except Exception as e:  # intentional: warmup non-critical
            logger.warning("[AutoTuner] Warmup failed (continuing): %s", e)

    async def run_probe_load(
        self,
        endpoint: str,
        model: str,
        config: TuningConfig,
        trial: optuna.trial.Trial | None,
        trial_id: int,
        broadcaster: _Broadcaster | None = None,
    ) -> tuple[float, float, float]:
        fast_requests = max(1, int(config.eval_requests * config.eval_fast_fraction))
        fast_config = LoadTestConfig(
            endpoint=endpoint,
            model=model,
            total_requests=fast_requests,
            concurrency=config.eval_concurrency,
            max_tokens=config.max_tokens,
            stream=True,
        )
        if broadcaster is not None:
            await broadcaster.broadcast(
                {
                    "type": "phase",
                    "data": {"trial_id": trial_id, "phase": "evaluating"},
                }
            )
        fast_result = await self._load_engine.run(fast_config)
        fast_score = self.compute_trial_score(fast_result, config)

        if trial is not None:
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
                max_tokens=config.max_tokens,
                stream=True,
            )
            full_result = await self._load_engine.run(full_config)
            score = self.compute_trial_score(full_result, config)
            tps = full_result.get("tps", {}).get("total", 0)
            p99_lat = full_result.get("latency", {}).get("p99", 9999)
        else:
            score = fast_score
            tps = fast_result.get("tps", {}).get("total", 0)
            p99_lat = fast_result.get("latency", {}).get("p99", 9999)

        return score, tps, p99_lat

    async def evaluate(
        self,
        endpoint: str,
        config: TuningConfig,
        trial: optuna.trial.Trial | None = None,
        trial_num: int = 0,
        broadcaster: _Broadcaster | None = None,
        model_resolver=resolve_model_name,
    ) -> tuple[float, float, float]:
        model_name = await model_resolver(endpoint)
        if not model_name or model_name == "auto":
            raise ValueError(f"Cannot resolve model name from {endpoint}. Ensure the vLLM endpoint is reachable.")
        _trial_id = trial.number if trial is not None and hasattr(trial, "number") else trial_num

        if config.warmup_requests > 0:
            await self.run_warmup_load(endpoint, model_name, config, _trial_id, broadcaster=broadcaster)

        score, tps, p99_lat = await self.run_probe_load(
            endpoint,
            model_name,
            config,
            trial,
            _trial_id,
            broadcaster=broadcaster,
        )
        return score, tps, p99_lat

    async def get_importance(
        self, study: optuna.Study | None, trials: list[optuna.trial.FrozenTrial]
    ) -> dict[str, Any]:
        if not study or len(trials) < 5:
            return {}
        try:
            importance = await asyncio.to_thread(optuna.importance.get_param_importances, study)
            return dict(importance)
        except (optuna.exceptions.OptunaError, RuntimeError, ValueError, TypeError) as e:
            logger.warning("[AutoTuner] get_importance failed: %s", e)
            return {}


def classify_failure_from_logs(logs: str | None) -> str:
    if not logs:
        return "unknown"
    low = logs.lower()
    if "out of memory" in low or "cuda out of memory" in low or "oom killer" in low:
        return "OOM"
    if any(kw in low for kw in ("invalid argument", "invalid configuration", "unrecognized", "unsupported")):
        return "invalid_config"
    if "timeout" in low or "timed out" in low or "deadline exceeded" in low:
        return "timeout"
    if "error" in low or "exception" in low or "traceback" in low or "crash" in low or "killed" in low:
        return "crash"
    return "unknown"


async def handle_trial_result_for_tuner(
    tuner: Any,  # AutoTuner — avoid circular import
    trial,
    trial_num: int,
    score,
    tps,
    p99_lat,
    trial_start,
    params,
    save_trial_fn,
) -> bool:
    assert tuner._config is not None
    if trial.should_prune():
        async with tuner._study_lock:
            assert tuner._study is not None
            tuner._study.tell(trial, state=optuna.trial.TrialState.PRUNED)
        t = TuningTrial(
            trial_id=trial_num, params=params, tps=tps, p99_latency=p99_lat, score=score, status="pruned", pruned=True
        )
        async with tuner._lock:
            tuner._trials.append(t)
            tuner._best_score_history.append(tuner._best_trial.score if tuner._best_trial else 0)
        try:
            await save_trial_fn(t)
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning("[AutoTuner] Failed to persist trial %d to storage: %s", trial_num, e)
            await tuner._broadcast_persistence_warning_once()
        await tuner._emit_trial_metrics(trial_start, "pruned")
        await tuner._broadcast(
            {
                "type": "trial_complete",
                "data": {"trial_id": trial_num, "score": score, "tps": tps, "p99_latency": p99_lat, "pruned": True},
            }
        )
        return True
    async with tuner._study_lock:
        assert tuner._study is not None
        tuner._study.tell(trial, score)
    t = TuningTrial(trial_id=trial_num, params=params, tps=tps, p99_latency=p99_lat, score=score, status="completed")
    async with tuner._lock:
        tuner._trials.append(t)
        if tuner._best_trial is None or score > tuner._best_trial.score:
            tuner._best_trial = t
        tuner._best_score_history.append(tuner._best_trial.score if tuner._best_trial else score)
    try:
        await save_trial_fn(t)
    except (OSError, RuntimeError, ValueError) as e:
        logger.warning("[AutoTuner] Failed to persist trial %d to storage: %s", trial_num, e)
        await tuner._broadcast_persistence_warning_once()
    await tuner._emit_trial_metrics(trial_start, "completed")
    await tuner._broadcast(
        {
            "type": "trial_complete",
            "data": {"trial_id": trial_num, "score": score, "tps": tps, "p99_latency": p99_lat, "pruned": False},
        }
    )
    return False


async def execute_trial_for_tuner(
    tuner: Any, trial_num: int, config: TuningConfig
) -> bool:  # AutoTuner — avoid circular import
    async with tuner._study_lock:
        assert tuner._study is not None
        trial = tuner._study.ask()
    params = tuner._suggest_params(trial, config)
    trial_start = time.monotonic()
    skip_reason: str | None = None
    skip_message = ""
    if kv_cache_oom_risk(params, config):
        skip_reason, skip_message = "OOM_predicted", "KV cache OOM 예측으로 건너뜁니다"
    elif (limit := first_violated_limit(params, config.learned_limits)) is not None:
        skip_reason = "learned_limit"
        skip_message = f"이전 기동 실패에서 학습한 상한({limit['param']} ≤ {limit['max']})을 넘어 건너뜁니다"
    if skip_reason:
        trial.set_user_attr("failure_reason", skip_reason)
        logger.info("[AutoTuner] Trial %d skipped: %s (params=%s)", trial_num, skip_reason, params)
        await tuner._broadcast(
            {
                "type": "tuning_warning",
                "data": {"message": f"Trial {trial_num}: {skip_message}", "trial": trial_num},
            }
        )
        async with tuner._study_lock:
            assert tuner._study is not None
            tuner._study.tell(trial, state=optuna.trial.TrialState.PRUNED)
        # Record the skip so the trials list reflects every trial the session asked for.
        t = TuningTrial(
            trial_id=trial_num,
            params=params,
            tps=0.0,
            p99_latency=0.0,
            score=0.0,
            status="skipped",
            pruned=True,
            failure={"reason": skip_reason, "diagnoses": [{"code": skip_reason, "title": skip_message, "fix": ""}]},
        )
        async with tuner._lock:
            tuner._trials.append(t)
            tuner._best_score_history.append(tuner._best_trial.score if tuner._best_trial else 0)
        try:
            await tuner._save_trial_fn()(t)
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning("[AutoTuner] Failed to persist trial %d to storage: %s", trial_num, e)
            await tuner._broadcast_persistence_warning_once()
        await tuner._emit_trial_metrics(trial_start, "skipped")
        await tuner._broadcast(
            {
                "type": "trial_complete",
                "data": {"trial_id": trial_num, "score": 0.0, "tps": 0.0, "p99_latency": 0.0, "pruned": True},
            }
        )
        return False
    await tuner._broadcast({"type": "trial_start", "data": {"trial_id": trial_num, "params": params}})
    if not await tuner._apply_trial_params(trial, trial_num, params):
        return True
    await tuner._broadcast({"type": "phase", "data": {"trial_id": trial_num, "phase": "restarting"}})
    await tuner._broadcast({"type": "phase", "data": {"trial_id": trial_num, "phase": "waiting_ready"}})
    if not await tuner._wait_for_isvc_ready(trial, trial_num):
        return True
    try:
        score, tps, p99_lat = await tuner._run_trial_evaluation(trial, trial_num)
    except Exception as e:  # intentional: trial evaluation recovery (specific errors caught earlier)
        logger.warning("[AutoTuner] Trial %d evaluation failed: %s", trial_num, e)
        failure_reason = "unknown"
        failure_logs: str | None = None
        if hasattr(tuner, "_read_failure_logs"):
            try:
                failure_logs = await tuner._read_failure_logs()
                failure_reason = classify_failure_from_logs(failure_logs)
                logger.debug("[AutoTuner] Trial %d failure classified as: %s", trial_num, failure_reason)
            except Exception:
                pass
        trial.set_user_attr("failure_reason", failure_reason)
        if hasattr(tuner, "_on_trial_failure"):
            try:
                await tuner._on_trial_failure(trial_num, params, failure_reason, failure_logs)
            except Exception as diag_err:
                logger.warning("[AutoTuner] Trial %d failure handling failed: %s", trial_num, diag_err)
        await tuner._broadcast(
            {
                "type": "error",
                "data": {
                    "message": f"Trial {trial_num} evaluation failed: {e}",
                    "recoverable": True,
                    "timestamp": time.time(),
                },
            }
        )
        await tuner._broadcast(
            {
                "type": "tuning_warning",
                "data": {"message": "트라이얼 평가 실패로 다음 트라이얼로 진행합니다", "trial": trial_num},
            }
        )
        async with tuner._study_lock:
            assert tuner._study is not None
            tuner._study.tell(trial, state=optuna.trial.TrialState.FAIL)
        return True
    await handle_trial_result_for_tuner(
        tuner, trial, trial_num, score, tps, p99_lat, trial_start, params, save_trial_fn=tuner._save_trial_fn()
    )
    return True


async def save_auto_benchmark_for_tuner(
    tuner: Any,  # AutoTuner — avoid circular import
    model_resolver=None,
    save_benchmark_fn=None,
) -> int | None:
    if model_resolver is None:
        model_resolver = resolve_model_name
    if tuner._best_trial is None or tuner._config is None:
        return None
    try:
        model_name = await model_resolver(tuner._vllm_endpoint)
    except httpx.ConnectError:
        model_name = "unknown"
    benchmark = Benchmark(
        name=f"auto-tune-{time.strftime('%Y%m%d-%H%M%S')}",
        config=LoadTestConfig(
            endpoint=tuner._vllm_endpoint,
            model=model_name,
            total_requests=tuner._config.eval_requests,
            concurrency=tuner._config.eval_concurrency,
            max_tokens=tuner._config.max_tokens,
            stream=True,
        ),
        result=LoadTestResult(
            total=tuner._config.eval_requests,
            total_requested=tuner._config.eval_requests,
            success=tuner._config.eval_requests,
            failed=0,
            latency=LatencyStats(mean=tuner._best_trial.p99_latency, p99=tuner._best_trial.p99_latency),
            tps=TpsStats(mean=tuner._best_trial.tps, total=tuner._best_trial.tps),
            tokens_per_sec=tuner._best_trial.tps,
        ),
    )
    if save_benchmark_fn is None:
        raise RuntimeError("save_benchmark_fn is required")
    return (await save_benchmark_fn(benchmark)).id


async def finalize_tuning_for_tuner(
    tuner: Any, auto_benchmark: bool = False
) -> int | None:  # AutoTuner — avoid circular import
    benchmark_id: int | None = None
    if tuner._best_trial and tuner._best_trial.score < 0 and tuner._config is not None:
        await tuner._broadcast(
            {
                "type": "tuning_warning",
                "data": {
                    "message": (
                        f"동시 사용자 {tuner._config.eval_concurrency}명에서 p99 ≤ {tuner._config.p99_latency_sla_ms}ms를 "
                        "만족한 설정이 없습니다. SLA 위반이 가장 작은 설정을 적용합니다. 동시 사용자 수나 출력 토큰 수를 줄이거나 자원을 늘리세요."
                    )
                },
            }
        )
    if tuner._best_trial:
        apply_result = await tuner._apply_params(tuner._best_trial.params)
        best_applied = not (isinstance(apply_result, dict) and not apply_result.get("success", True))
        best_ready = best_applied and (await tuner._wait_for_ready()) is not False
        if not best_ready:
            logger.warning("[AutoTuner] Best params were not applied or the service is not ready; skipping benchmark")
            await tuner._broadcast(
                {
                    "type": "tuning_warning",
                    "data": {"message": "최적 파라미터 적용 또는 서비스 준비에 실패했습니다. 현재 설정을 확인하세요"},
                }
            )
        if auto_benchmark and best_ready:
            try:
                benchmark_id = await tuner._save_auto_benchmark()
                if benchmark_id is not None:
                    await tuner._broadcast({"type": "benchmark_saved", "data": {"benchmark_id": benchmark_id}})
                else:
                    await tuner._broadcast(
                        {"type": "tuning_warning", "data": {"message": "자동 벤치마크 저장 ID를 확인할 수 없습니다"}}
                    )
            except (OSError, RuntimeError, ValueError, TunerError) as e:
                logger.warning("[AutoTuner] Auto benchmark save failed: %s", e)
                await tuner._broadcast(
                    {"type": "tuning_warning", "data": {"message": "자동 벤치마크 저장에 실패했습니다"}}
                )
    await tuner._broadcast(
        {
            "type": "tuning_complete",
            "data": {
                "best_params": tuner._best_trial.params if tuner._best_trial else {},
                "total_trials": len(tuner._trials),
            },
        }
    )
    return benchmark_id
