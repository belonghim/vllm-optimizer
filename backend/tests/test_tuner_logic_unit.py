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


@pytest.mark.asyncio
async def test_setup_study_creates_maximize_study() -> None:
    logic = TunerLogic(_make_load_engine())

    direction, study = await logic.setup_study(TuningConfig(), storage_url=None)

    assert direction == "maximize"
    assert isinstance(study, optuna.Study)
    assert study.direction == optuna.study.StudyDirection.MAXIMIZE


def test_compute_trial_score_is_tps_within_sla() -> None:
    logic = TunerLogic(_make_load_engine())
    config = TuningConfig(p99_latency_sla_ms=500)

    assert logic.compute_trial_score({"tps": {"total": 42.0}, "latency": {"p99": 0.3}}, config) == 42.0


def test_compute_trial_score_sla_violation_ranks_below_feasible() -> None:
    logic = TunerLogic(_make_load_engine())
    config = TuningConfig(p99_latency_sla_ms=500)

    feasible = logic.compute_trial_score({"tps": {"total": 1.0}, "latency": {"p99": 0.4}}, config)
    violating = logic.compute_trial_score({"tps": {"total": 10000.0}, "latency": {"p99": 0.9}}, config)
    worse = logic.compute_trial_score({"tps": {"total": 10000.0}, "latency": {"p99": 2.0}}, config)

    assert feasible > violating > worse
    assert violating == pytest.approx(-1.8)


def test_suggest_params_searches_throughput_knobs_and_fixes_max_model_len() -> None:
    logic = TunerLogic(_make_load_engine())
    config = TuningConfig(max_model_len=4096)
    trial = optuna.create_study(direction="maximize").ask()

    params = logic.suggest_params(trial, config)

    assert set(params) == {"max_num_seqs", "gpu_memory_utilization", "max_num_batched_tokens", "max_model_len"}
    assert params["max_model_len"] == 4096
    assert "max_model_len" not in trial.params


@pytest.mark.asyncio
async def test_probe_load_uses_closed_loop_concurrency_and_output_tokens() -> None:
    engine = _make_load_engine()
    logic = TunerLogic(engine)
    config = TuningConfig(eval_concurrency=24, max_tokens=128, eval_requests=10)

    await logic.run_probe_load("http://x", "m", config, trial=None, trial_id=0)

    for call in engine.run.await_args_list:
        load = call.args[0]
        assert (load.concurrency, load.max_tokens, load.rps) == (24, 128, 0)
