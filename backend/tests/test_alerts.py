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
        ),
    )
    metrics = SimpleNamespace(
        p99_e2e_latency_ms=750.0,
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
    assert violated_names == {"p99_latency_ms"}


def test_sla_violations_ttft_and_tpot_thresholds(isolated_client: TestClient):
    profile = SlaProfile(
        id=4,
        name="ttft-tpot",
        thresholds=SlaThresholds(mean_ttft_max_ms=200.0, p95_tpot_max_ms=50.0, mean_queue_time_max_ms=1000.0),
    )
    metrics = SimpleNamespace(
        p99_e2e_latency_ms=0.0,
        mean_ttft_ms=350.0,
        p99_ttft_ms=900.0,
        mean_tpot_ms=10.0,
        p99_tpot_ms=80.0,
        mean_queue_time_ms=5.0,
    )

    with patch("routers.alerts.storage.list_sla_profiles", new=AsyncMock(return_value=[profile])):
        with patch("routers.alerts.metrics_collector", SimpleNamespace(latest=metrics)):
            response = isolated_client.get("/api/alerts/sla-violations")

    payload = SlaViolationsResponse.model_validate(response.json())
    assert {v.metric for v in payload.violations[0].violated_metrics} == {"mean_ttft_max_ms", "p95_tpot_max_ms"}


def test_sla_violations_no_violation(isolated_client: TestClient):
    profile = SlaProfile(
        id=2,
        name="normal",
        thresholds=SlaThresholds(
            p95_latency_max_ms=900.0,
        ),
    )
    metrics = SimpleNamespace(
        p99_e2e_latency_ms=400.0,
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
        thresholds=SlaThresholds(p95_latency_max_ms=500.0),
    )

    with patch("routers.alerts.storage.list_sla_profiles", new=AsyncMock(return_value=[profile])):
        with patch("routers.alerts.metrics_collector", SimpleNamespace(latest=None)):
            response = isolated_client.get("/api/alerts/sla-violations")

    assert response.status_code == 200
    payload = SlaViolationsResponse.model_validate(response.json())
    assert payload.has_violations is False
    assert payload.violations == []
