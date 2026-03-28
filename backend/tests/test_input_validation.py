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
                objective="balanced",
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
                objective="balanced",
                n_trials=0,
                eval_requests=100,
                vllm_endpoint="http://localhost:8000",
            )
        errors = exc_info.value.errors()
        assert any("greater than or equal to 1" in str(e) for e in errors)

    def test_n_trials_within_bounds(self):
        """n_trials=50 should pass validation."""
        req = TuningStartRequest(
            objective="balanced",
            n_trials=50,
            eval_requests=100,
            vllm_endpoint="http://localhost:8000",
        )
        assert req.n_trials == 50

    def test_eval_requests_exceeds_upper_bound(self):
        """eval_requests=2000 should fail validation (max 1000)."""
        with pytest.raises(ValidationError) as exc_info:
            TuningStartRequest(
                objective="balanced",
                n_trials=10,
                eval_requests=2000,
                vllm_endpoint="http://localhost:8000",
            )
        errors = exc_info.value.errors()
        assert any("less than or equal to 1000" in str(e) for e in errors)

    def test_eval_concurrency_exceeds_upper_bound(self):
        """eval_concurrency=256 should fail validation (max 128)."""
        with pytest.raises(ValidationError) as exc_info:
            TuningStartRequest(
                objective="balanced",
                n_trials=10,
                eval_requests=100,
                vllm_endpoint="http://localhost:8000",
                eval_concurrency=256,
            )
        errors = exc_info.value.errors()
        assert any("less than or equal to 128" in str(e) for e in errors)

    def test_eval_rps_exceeds_upper_bound(self):
        """eval_rps=600.0 should fail validation (max 500.0)."""
        with pytest.raises(ValidationError) as exc_info:
            TuningStartRequest(
                objective="balanced",
                n_trials=10,
                eval_requests=100,
                vllm_endpoint="http://localhost:8000",
                eval_rps=600.0,
            )
        errors = exc_info.value.errors()
        assert any("less than or equal to 500" in str(e) for e in errors)

    def test_eval_rps_below_lower_bound(self):
        """eval_rps=0.05 should fail validation (min 0.1)."""
        with pytest.raises(ValidationError) as exc_info:
            TuningStartRequest(
                objective="balanced",
                n_trials=10,
                eval_requests=100,
                vllm_endpoint="http://localhost:8000",
                eval_rps=0.05,
            )
        errors = exc_info.value.errors()
        assert any("greater than or equal to 0.1" in str(e) for e in errors)


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
        """eval_concurrency=256 should fail validation (max 128)."""
        with pytest.raises(ValidationError) as exc_info:
            TuningConfig(eval_concurrency=256)
        errors = exc_info.value.errors()
        assert any("less than or equal to 128" in str(e) for e in errors)

    def test_eval_rps_exceeds_upper_bound(self):
        """eval_rps=750 should fail validation (max 500)."""
        with pytest.raises(ValidationError) as exc_info:
            TuningConfig(eval_rps=750)
        errors = exc_info.value.errors()
        assert any("less than or equal to 500" in str(e) for e in errors)

    def test_tuning_config_within_bounds(self):
        """Valid config with n_trials=50, eval_requests=500 should pass."""
        config = TuningConfig(n_trials=50, eval_requests=500, eval_concurrency=64, eval_rps=100)
        assert config.n_trials == 50
        assert config.eval_requests == 500
        assert config.eval_concurrency == 64
        assert config.eval_rps == 100


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
