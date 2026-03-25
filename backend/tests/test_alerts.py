from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from models.sla import SlaProfile, SlaThresholds
from routers.alerts import SlaViolationsResponse


def test_sla_violations_with_violation(isolated_client: TestClient):
    profile = SlaProfile(
        id=1,
        name="strict-latency",
        thresholds=SlaThresholds(
            p95_latency_max_ms=500.0,
            min_tps=10.0,
        ),
    )
    metrics = SimpleNamespace(
        p99_e2e_latency_ms=750.0,
        tokens_per_second=5.0,
        error_rate_pct=None,
        p99_ttft_ms=None,
    )

    with patch("routers.alerts.storage.list_sla_profiles", new=AsyncMock(return_value=[profile])):
        with patch("routers.alerts.metrics_collector", SimpleNamespace(latest=metrics)):
            response = isolated_client.get("/api/alerts/sla-violations")

    assert response.status_code == 200
    payload = SlaViolationsResponse.model_validate(response.json())
    assert payload.has_violations is True
    violations = payload.violations
    assert len(violations) == 1
    assert violations[0].profile_id == 1
    violated_names = {v.metric for v in violations[0].violated_metrics}
    assert violated_names == {"p99_latency_ms", "min_tps"}


def test_sla_violations_no_violation(isolated_client: TestClient):
    profile = SlaProfile(
        id=2,
        name="normal",
        thresholds=SlaThresholds(
            p95_latency_max_ms=900.0,
            min_tps=2.0,
        ),
    )
    metrics = SimpleNamespace(
        p99_e2e_latency_ms=400.0,
        tokens_per_second=20.0,
        error_rate_pct=None,
        p99_ttft_ms=None,
    )

    with patch("routers.alerts.storage.list_sla_profiles", new=AsyncMock(return_value=[profile])):
        with patch("routers.alerts.metrics_collector", SimpleNamespace(latest=metrics)):
            response = isolated_client.get("/api/alerts/sla-violations")

    assert response.status_code == 200
    payload = SlaViolationsResponse.model_validate(response.json())
    assert payload.has_violations is False
    assert payload.violations == []


def test_sla_violations_no_metrics(isolated_client: TestClient):
    profile = SlaProfile(
        id=3,
        name="requires-metrics",
        thresholds=SlaThresholds(min_tps=10.0),
    )

    with patch("routers.alerts.storage.list_sla_profiles", new=AsyncMock(return_value=[profile])):
        with patch("routers.alerts.metrics_collector", SimpleNamespace(latest=None)):
            response = isolated_client.get("/api/alerts/sla-violations")

    assert response.status_code == 200
    payload = SlaViolationsResponse.model_validate(response.json())
    assert payload.has_violations is False
    assert payload.violations == []
