import time

import pytest
from fastapi.testclient import TestClient

from ..main import app
from ..services.multi_target_collector import VLLMMetrics


@pytest.fixture
def client():
    return TestClient(app)


def test_metrics_latest_endpoint(client):
    response = client.get("/api/metrics/latest")
    assert response.status_code == 200
    data = response.json()
    # Basic shape checks
    assert "timestamp" in data
    assert "tps" in data
    assert "latency_mean" in data


def test_metrics_history_endpoint_returns_list(client):
    response = client.get("/api/metrics/history?last_n=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_metrics_history_endpoint_handles_nan_gracefully(client):
    # Inject a VLLMMetrics with NaN values into the collector's history
    from ..services.shared import multi_target_collector

    # Create a metrics object with NaN latency values
    nan_metrics = VLLMMetrics(
        timestamp=time.time(),
        tokens_per_second=100.0,
        requests_per_second=10.0,
        mean_ttft_ms=float("nan"),
        p99_ttft_ms=float("nan"),
        mean_e2e_latency_ms=float("nan"),
        p99_e2e_latency_ms=float("nan"),
        kv_cache_usage_pct=50.0,
        kv_cache_hit_rate=0.8,
        running_requests=5,
        waiting_requests=2,
        gpu_memory_used_gb=10.0,
        gpu_memory_total_gb=40.0,
        gpu_utilization_pct=75.0,
        pod_count=3,
        pod_ready=3,
    )

    default_target = multi_target_collector._get_default_target()
    assert default_target is not None
    default_target.history.append(nan_metrics)

    # Call /api/metrics/history — should return 200, not 500
    response = client.get("/api/metrics/history?last_n=5")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Verify response body does NOT contain literal "NaN" string
    response_text = response.text
    assert "NaN" not in response_text, "Response should not contain literal NaN string"

    # Verify response is valid JSON
    data = response.json()
    assert isinstance(data, list)


def test_metrics_batch_endpoint(isolated_client):
    response = isolated_client.post(
        "/api/metrics/batch",
        json={"targets": [{"namespace": "llm-d-demo", "inferenceService": "small-llm-d"}]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "llm-d-demo/small-llm-d" in data["results"]
    target_result = data["results"]["llm-d-demo/small-llm-d"]
    assert "status" in target_result
    assert target_result["status"] in ("collecting", "ready")


def test_metrics_batch_endpoint_empty_targets(isolated_client):
    response = isolated_client.post(
        "/api/metrics/batch",
        json={"targets": []},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == {}


def test_metrics_batch_endpoint_multiple_targets(isolated_client):
    response = isolated_client.post(
        "/api/metrics/batch",
        json={
            "targets": [
                {"namespace": "ns1", "inferenceService": "is1"},
                {"namespace": "ns2", "inferenceService": "is2"},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "ns1/is1" in data["results"]
    assert "ns2/is2" in data["results"]
