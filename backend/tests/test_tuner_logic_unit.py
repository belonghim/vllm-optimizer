from unittest.mock import AsyncMock, MagicMock

import optuna
import pytest

from ..models.load_test import TuningConfig
from ..services.tuner_logic import TunerLogic  # pyright: ignore[reportImplicitRelativeImport]  # test env: backend/ added to sys.path at runtime


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
async def test_setup_study_latency_creates_minimize_study() -> None:
    logic = TunerLogic(_make_load_engine())
    config = _default_config("latency")

    direction, study = await logic.setup_study(config, storage_url=None)

    assert direction == "minimize"
    assert study.direction == optuna.study.StudyDirection.MINIMIZE


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
