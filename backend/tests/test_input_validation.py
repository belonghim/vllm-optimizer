"""
Input validation tests for Pydantic Field constraints.

Tests upper-bound (le) constraints on numeric fields in:
- TuningStartRequest
- TuningConfig
- LoadTestConfig
"""

import pytest
from pydantic import ValidationError

from ..models.load_test import LoadTestConfig, TuningConfig
from ..routers.tuner import TuningStartRequest


class TestTuningStartRequestValidation:
    """Test upper-bound constraints on TuningStartRequest fields."""

    def test_n_trials_exceeds_upper_bound(self):
        """n_trials=999 should fail validation (max 100)."""
        with pytest.raises(ValidationError) as exc_info:
            TuningStartRequest(
                n_trials=999,
                eval_requests=100,
                vllm_endpoint="http://localhost:8000",
            )
        errors = exc_info.value.errors()
        assert any("less than or equal to 100" in str(e) for e in errors)

    def test_n_trials_below_lower_bound(self):
        """n_trials=0 should fail validation (min 1)."""
        with pytest.raises(ValidationError) as exc_info:
            TuningStartRequest(
                n_trials=0,
                eval_requests=100,
                vllm_endpoint="http://localhost:8000",
            )
        errors = exc_info.value.errors()
        assert any("greater than or equal to 1" in str(e) for e in errors)

    def test_n_trials_within_bounds(self):
        """n_trials=50 should pass validation."""
        req = TuningStartRequest(
            n_trials=50,
            eval_requests=100,
            vllm_endpoint="http://localhost:8000",
        )
        assert req.n_trials == 50

    def test_eval_requests_exceeds_upper_bound(self):
        """eval_requests=2000 should fail validation (max 1000)."""
        with pytest.raises(ValidationError) as exc_info:
            TuningStartRequest(
                n_trials=10,
                eval_requests=2000,
                vllm_endpoint="http://localhost:8000",
            )
        errors = exc_info.value.errors()
        assert any("less than or equal to 1000" in str(e) for e in errors)

    def test_eval_concurrency_exceeds_upper_bound(self):
        with pytest.raises(ValidationError) as exc_info:
            TuningStartRequest(n_trials=10, eval_requests=100, eval_concurrency=1024)
        errors = exc_info.value.errors()
        assert any("less than or equal to 512" in str(e) for e in errors)

    def test_sla_below_lower_bound(self):
        with pytest.raises(ValidationError) as exc_info:
            TuningStartRequest(n_trials=10, p99_latency_sla_ms=10)
        errors = exc_info.value.errors()
        assert any("greater than or equal to 100" in str(e) for e in errors)


class TestTuningConfigValidation:
    """Test upper-bound constraints on TuningConfig fields."""

    def test_n_trials_exceeds_upper_bound(self):
        """n_trials=150 should fail validation (max 100)."""
        with pytest.raises(ValidationError) as exc_info:
            TuningConfig(n_trials=150)
        errors = exc_info.value.errors()
        assert any("less than or equal to 100" in str(e) for e in errors)

    def test_eval_requests_exceeds_upper_bound(self):
        """eval_requests=5000 should fail validation (max 1000)."""
        with pytest.raises(ValidationError) as exc_info:
            TuningConfig(eval_requests=5000)
        errors = exc_info.value.errors()
        assert any("less than or equal to 1000" in str(e) for e in errors)

    def test_eval_concurrency_exceeds_upper_bound(self):
        with pytest.raises(ValidationError) as exc_info:
            TuningConfig(eval_concurrency=1024)
        errors = exc_info.value.errors()
        assert any("less than or equal to 512" in str(e) for e in errors)

    def test_max_model_len_above_model_limit_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            TuningConfig(max_model_len=65536, model_max_position_embeddings=32768)
        assert "exceeds the model limit" in str(exc_info.value)

    def test_tuning_config_within_bounds(self):
        config = TuningConfig(n_trials=50, eval_requests=500, eval_concurrency=64, p99_latency_sla_ms=5000)
        assert config.n_trials == 50
        assert config.eval_requests == 500
        assert config.eval_concurrency == 64
        assert config.objective_label == "p99<=5000ms@64users"


class TestLoadTestConfigValidation:
    """Test upper-bound constraints on LoadTestConfig fields."""

    def test_concurrency_exceeds_upper_bound(self):
        with pytest.raises(ValidationError) as exc_info:
            LoadTestConfig(concurrency=1001)
        errors = exc_info.value.errors()
        assert any("less than or equal to 1000" in str(e) for e in errors)

    def test_duration_exceeds_upper_bound(self):
        """duration=7200 should fail validation (max 3600)."""
        with pytest.raises(ValidationError) as exc_info:
            LoadTestConfig(duration=7200)
        errors = exc_info.value.errors()
        assert any("less than or equal to 3600" in str(e) for e in errors)

    def test_duration_below_lower_bound(self):
        """duration=0 should fail validation (min 1)."""
        with pytest.raises(ValidationError) as exc_info:
            LoadTestConfig(duration=0)
        errors = exc_info.value.errors()
        assert any("greater than or equal to 1" in str(e) for e in errors)

    def test_concurrency_within_bounds(self):
        """concurrency=250 should pass validation."""
        config = LoadTestConfig(concurrency=250)
        assert config.concurrency == 250

    def test_duration_within_bounds(self):
        """duration=300 should pass validation."""
        config = LoadTestConfig(duration=300)
        assert config.duration == 300

    def test_load_test_config_within_bounds(self):
        """Valid config with concurrency=100, duration=60 should pass."""
        config = LoadTestConfig(concurrency=100, duration=60, total_requests=200)
        assert config.concurrency == 100
        assert config.duration == 60
        assert config.total_requests == 200
