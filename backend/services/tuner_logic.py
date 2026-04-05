import asyncio
import logging
import math
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import httpx
import optuna
from errors import TunerError  # pyright: ignore[reportImplicitRelativeImport]  # backend/ added to sys.path at runtime
from models.load_test import (  # pyright: ignore[reportImplicitRelativeImport]  # backend/ added to sys.path at runtime
    Benchmark,
    LatencyStats,
    LoadTestConfig,
    LoadTestResult,
    SweepConfig,
    TpsStats,
    TuningConfig,
    TuningTrial,
)
from services.load_engine import (
    LoadTestEngine,  # pyright: ignore[reportImplicitRelativeImport]  # backend/ added to sys.path at runtime
)

from .model_resolver import resolve_model_name

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger = logging.getLogger(__name__)

_EvalFn = Callable[
    [str, TuningConfig, optuna.trial.Trial | None, int],
    Awaitable[tuple[float, float, float]],
]


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
                study = await asyncio.to_thread(  # type: ignore[arg-type]  # optuna.create_study returns Study|None, pyright can't track through to_thread
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
                    study = optuna.create_study(sampler=sampler, pruner=pruner, **direction_kwarg)  # type: ignore[arg-type]  # direction_kwarg is dict, pyright can't verify TypedDict keys
                except optuna.exceptions.OptunaError as e:
                    raise TunerError(
                        "Optuna study initialization failed after storage fallback",
                        detail={"storage_url": storage_url, "objective": config.objective},
                    ) from e
        else:
            try:
                study = optuna.create_study(sampler=sampler, pruner=pruner, **direction_kwarg)  # type: ignore[arg-type]  # direction_kwarg is dict, pyright can't verify TypedDict keys
            except optuna.exceptions.OptunaError as e:
                raise TunerError(
                    "Optuna study initialization failed",
                    detail={"storage_url": storage_url, "objective": config.objective},
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

    def compute_trial_score(self, result: dict[str, Any], config: TuningConfig) -> float:
        tps = result.get("tps", {}).get("total", 0)
        p99_lat = result.get("latency", {}).get("p99", 9999)
        if config.objective == "tps":
            return tps
        if config.objective == "latency":
            return -p99_lat
        return tps / (p99_lat + 1) * 100

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
            rps=config.eval_rps,
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
            rps=config.eval_rps,
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
            raise ValueError(f"Cannot resolve model name from {endpoint}. Set VLLM_MODEL env var.")
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

    async def objective(
        self,
        endpoint: str,
        config: TuningConfig,
        evaluation_mode: str,
        sweep_config: SweepConfig | None,
        trial: optuna.trial.Trial | None = None,
        trial_num: int = 0,
        broadcaster: _Broadcaster | None = None,
        evaluate_fn: _EvalFn | None = None,
    ) -> tuple[float, float, float]:
        if evaluation_mode == "sweep":
            if sweep_config is None:
                raise TunerError(
                    "Sweep evaluation requires sweep_config",
                    detail={"evaluation_mode": evaluation_mode},
                )
            _trial_id = trial.number if trial is not None and hasattr(trial, "number") else trial_num
            if broadcaster is not None:
                await broadcaster.broadcast(
                    {
                        "type": "phase",
                        "data": {"trial_id": _trial_id, "phase": "evaluating"},
                    }
                )
            sweep_result = await self._load_engine.run_sweep(sweep_config)
            score = float(sweep_result.optimal_rps or 0.0)
            if trial is not None and config.objective != "pareto":
                trial.report(score, step=0)
            return score, score, 0.0

        evaluator = evaluate_fn if evaluate_fn is not None else self.evaluate
        return await evaluator(endpoint, config, trial=trial, trial_num=trial_num)

    async def get_importance(
        self, study: optuna.Study | None, trials: list[optuna.trial.FrozenTrial]
    ) -> dict[str, Any]:
        if not study or len(trials) < 5:
            return {}
        try:
            if hasattr(study, "directions") and len(getattr(study, "directions", [])) > 1:
                return {}
        except optuna.exceptions.OptunaError as e:
            logger.warning("[AutoTuner] Multi-objective check failed: %s", e)
        try:
            importance = await asyncio.to_thread(optuna.importance.get_param_importances, study)
            return dict(importance)
        except (optuna.exceptions.OptunaError, RuntimeError, ValueError, TypeError) as e:
            logger.warning("[AutoTuner] get_importance failed: %s", e)
            return {}


async def update_pareto_front_for_tuner(tuner: Any) -> None:  # AutoTuner — avoid circular import
    try:
        assert tuner._study is not None
        pareto = {t.number for t in tuner._study.best_trials}
        async with tuner._lock:
            for recorded in tuner._trials:
                recorded.is_pareto_optimal = recorded.trial_id in pareto
        tuner._pareto_front_size = len(pareto)
    except (optuna.exceptions.OptunaError, RuntimeError, ValueError, TypeError) as e:
        logger.warning("[AutoTuner] Pareto front update failed: %s", e)


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
    if tuner._config.objective != "pareto" and trial.should_prune():
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
    if tuner._config.objective == "pareto":
        async with tuner._study_lock:
            assert tuner._study is not None
            tuner._study.tell(trial, [tps, p99_lat])
        score = tps / (p99_lat + 1) * 100
    else:
        async with tuner._study_lock:
            assert tuner._study is not None
            tuner._study.tell(trial, score)
    t = TuningTrial(trial_id=trial_num, params=params, tps=tps, p99_latency=p99_lat, score=score, status="completed")
    async with tuner._lock:
        tuner._trials.append(t)
        if (
            tuner._best_trial is None
            or (tuner._direction == "maximize" and score > tuner._best_trial.score)
            or (tuner._direction == "minimize" and score < tuner._best_trial.score)
        ):
            tuner._best_trial = t
        tuner._best_score_history.append(tuner._best_trial.score if tuner._best_trial else score)
    try:
        await save_trial_fn(t)
    except (OSError, RuntimeError, ValueError) as e:
        logger.warning("[AutoTuner] Failed to persist trial %d to storage: %s", trial_num, e)
        await tuner._broadcast_persistence_warning_once()
    await tuner._emit_trial_metrics(trial_start, "completed")
    if tuner._config.objective == "pareto":
        await update_pareto_front_for_tuner(tuner)
    await tuner._broadcast(
        {
            "type": "trial_complete",
            "data": {"trial_id": trial_num, "score": score, "tps": tps, "p99_latency": p99_lat, "pruned": False},
        }
    )
    return False


async def execute_trial_for_tuner(
    tuner: Any, trial_num: int, config: TuningConfig
) -> None:  # AutoTuner — avoid circular import
    async with tuner._study_lock:
        assert tuner._study is not None
        trial = tuner._study.ask()
    params = tuner._suggest_params(trial, config)
    trial_start = time.monotonic()
    await tuner._broadcast({"type": "trial_start", "data": {"trial_id": trial_num, "params": params}})
    if not await tuner._apply_trial_params(trial, trial_num, params):
        return
    await tuner._broadcast({"type": "phase", "data": {"trial_id": trial_num, "phase": "restarting"}})
    await tuner._broadcast({"type": "phase", "data": {"trial_id": trial_num, "phase": "waiting_ready"}})
    if not await tuner._wait_for_isvc_ready(trial, trial_num):
        return
    try:
        score, tps, p99_lat = await tuner._run_trial_evaluation(trial, trial_num)
    except Exception as e:  # intentional: trial evaluation recovery (specific errors caught earlier)
        logger.warning("[AutoTuner] Trial %d evaluation failed: %s", trial_num, e)
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
        return
    await handle_trial_result_for_tuner(
        tuner, trial, trial_num, score, tps, p99_lat, trial_start, params, save_trial_fn=tuner._save_trial_fn()
    )


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
        model_name = os.environ.get("VLLM_MODEL", "unknown")
    benchmark = Benchmark(
        name=f"auto-tune-{time.strftime('%Y%m%d-%H%M%S')}",
        config=LoadTestConfig(
            endpoint=tuner._vllm_endpoint,
            model=model_name,
            total_requests=tuner._config.eval_requests,
            concurrency=tuner._config.eval_concurrency,
            rps=tuner._config.eval_rps,
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
    if tuner._best_trial:
        await tuner._apply_params(tuner._best_trial.params)
        await tuner._wait_for_ready()
        if auto_benchmark:
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
