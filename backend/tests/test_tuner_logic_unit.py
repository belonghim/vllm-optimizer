from unittest.mock import AsyncMock, MagicMock

import optuna
import pytest

from ..models.load_test import TuningConfig
from ..services.tuner_logic import (
    TunerLogic,  # pyright: ignore[reportImplicitRelativeImport]  # test env: backend/ added to sys.path at runtime
)


def _make_load_engine() -> MagicMock:
    engine = MagicMock()
    engine.run = AsyncMock(return_value={"tps": {"total": 50.0}, "latency": {"p99": 0.5}})
    return engine


def _default_config(objective: str = "tps") -> TuningConfig:
    return TuningConfig(objective=objective)


@pytest.mark.asyncio
async def test_setup_study_tps_creates_maximize_study() -> None:
    logic = TunerLogic(_make_load_engine())
    config = _default_config("tps")

    direction, study = await logic.setup_study(config, storage_url=None)

    assert direction == "maximize"
    assert isinstance(study, optuna.Study)
    assert study.direction == optuna.study.StudyDirection.MAXIMIZE


@pytest.mark.asyncio
@pytest.mark.parametrize("objective", ["latency", "balanced", "sla_tps"])
async def test_setup_study_signed_score_objectives_maximize(objective: str) -> None:
    logic = TunerLogic(_make_load_engine())
    config = _default_config(objective)

    direction, study = await logic.setup_study(config, storage_url=None)

    assert direction == "maximize"
    assert study.direction == optuna.study.StudyDirection.MAXIMIZE


def test_compute_trial_score_latency_prefers_lower_p99() -> None:
    logic = TunerLogic(_make_load_engine())
    config = _default_config("latency")

    fast = logic.compute_trial_score({"tps": {"total": 1.0}, "latency": {"p99": 0.2}}, config)
    slow = logic.compute_trial_score({"tps": {"total": 1.0}, "latency": {"p99": 2.0}}, config)

    assert fast > slow


def test_compute_trial_score_sla_violation_ranks_below_feasible() -> None:
    logic = TunerLogic(_make_load_engine())
    config = _default_config("sla_tps")
    config.p99_latency_sla_ms = 500

    feasible = logic.compute_trial_score({"tps": {"total": 1.0}, "latency": {"p99": 0.4}}, config)
    violating = logic.compute_trial_score({"tps": {"total": 10000.0}, "latency": {"p99": 0.9}}, config)

    assert feasible > violating


def test_suggest_params_returns_all_required_keys() -> None:
    logic = TunerLogic(_make_load_engine())
    config = _default_config("tps")
    study = optuna.create_study(direction="maximize")
    trial = study.ask()

    params = logic.suggest_params(trial, config)

    assert "max_num_seqs" in params
    assert "gpu_memory_utilization" in params
    assert "max_model_len" in params
    assert "enable_chunked_prefill" in params
    assert "enable_enforce_eager" in params
    assert "max_num_batched_tokens" in params


def test_compute_trial_score_tps_objective() -> None:
    logic = TunerLogic(_make_load_engine())
    config = _default_config("tps")
    result = {"tps": {"total": 42.0}, "latency": {"p99": 0.3}}

    score = logic.compute_trial_score(result, config)

    assert score == 42.0


def test_compute_trial_score_latency_objective_negates_p99() -> None:
    logic = TunerLogic(_make_load_engine())
    config = _default_config("latency")
    result = {"tps": {"total": 10.0}, "latency": {"p99": 1.5}}

    score = logic.compute_trial_score(result, config)

    assert score == -1.5
