import asyncio
import time

import httpx
import pytest

pytestmark = pytest.mark.slow
from unittest.mock import AsyncMock, MagicMock, patch

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
        json={"targets": [{"namespace": "test-ns", "inferenceService": "test-isvc"}]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "test-ns/test-isvc/inferenceservice" in data["results"]
    target_result = data["results"]["test-ns/test-isvc/inferenceservice"]
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


def test_time_range_config_includes_1h():
    from routers.metrics import _TIME_RANGE_CONFIG

    assert "1h" in _TIME_RANGE_CONFIG
    assert _TIME_RANGE_CONFIG["1h"]["duration"] == 3600
    assert _TIME_RANGE_CONFIG["1h"]["step"] == 10


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
    assert "ns1/is1/inferenceservice" in data["results"]
    assert "ns2/is2/inferenceservice" in data["results"]


def test_metrics_batch_default_60_points(isolated_client):
    response = isolated_client.post(
        "/api/metrics/batch",
        json={"targets": [{"namespace": "test-ns", "inferenceService": "test-isvc"}]},
    )
    assert response.status_code == 200
    data = response.json()
    target_result = data["results"]["test-ns/test-isvc/inferenceservice"]
    assert "history" in target_result
    assert len(target_result["history"]) <= 60


def test_metrics_batch_custom_history_points(isolated_client):
    response = isolated_client.post(
        "/api/metrics/batch",
        json={
            "targets": [{"namespace": "test-ns", "inferenceService": "test-isvc"}],
            "history_points": 200,
        },
    )
    assert response.status_code == 200
    data = response.json()
    target_result = data["results"]["test-ns/test-isvc/inferenceservice"]
    assert "history" in target_result
    assert len(target_result["history"]) <= 200


def test_metrics_batch_caps_at_max(isolated_client):
    response = isolated_client.post(
        "/api/metrics/batch",
        json={
            "targets": [{"namespace": "test-ns", "inferenceService": "test-isvc"}],
            "history_points": 1000,
        },
    )
    assert response.status_code == 200
    data = response.json()
    target_result = data["results"]["test-ns/test-isvc/inferenceservice"]
    assert "history" in target_result
    assert len(target_result["history"]) <= 1000


def _make_async_client_mock(get_mock):
    mock_ac = AsyncMock()
    mock_ac.get = get_mock
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_ac)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


def test_metrics_batch_endpoint_with_llmisvc_cr_type(isolated_client, monkeypatch):
    from services.shared import multi_target_collector

    call_args = []

    async def mock_get_metrics(namespace, is_name, cr_type=None):
        call_args.append({"namespace": namespace, "is_name": is_name, "cr_type": cr_type})
        return await multi_target_collector.get_metrics.__wrapped__(namespace, is_name, cr_type)

    original = multi_target_collector.get_metrics

    async def mock_get_metrics_v2(namespace, is_name, cr_type=None):
        call_args.append({"namespace": namespace, "is_name": is_name, "cr_type": cr_type})
        return None

    monkeypatch.setattr(multi_target_collector, "get_metrics", mock_get_metrics_v2)

    response = isolated_client.post(
        "/api/metrics/batch",
        json={"targets": [{"namespace": "test-ns", "inferenceService": "llm-svc", "cr_type": "llminferenceservice"}]},
    )
    assert response.status_code == 200
    data = response.json()

    assert "test-ns/llm-svc/llminferenceservice" in data["results"]
    assert len(call_args) >= 1
    assert call_args[0]["cr_type"] == "llminferenceservice"
    assert call_args[0]["namespace"] == "test-ns"
    assert call_args[0]["is_name"] == "llm-svc"


def test_metrics_batch_endpoint_with_inferenceservice_cr_type(isolated_client, monkeypatch):
    from services.shared import multi_target_collector

    call_args = []

    async def mock_get_metrics(namespace, is_name, cr_type=None):
        call_args.append({"namespace": namespace, "is_name": is_name, "cr_type": cr_type})
        return None

    monkeypatch.setattr(multi_target_collector, "get_metrics", mock_get_metrics)

    response = isolated_client.post(
        "/api/metrics/batch",
        json={"targets": [{"namespace": "test-ns", "inferenceService": "isvc-svc", "cr_type": "inferenceservice"}]},
    )
    assert response.status_code == 200
    data = response.json()

    assert "test-ns/isvc-svc/inferenceservice" in data["results"]
    assert len(call_args) >= 1
    assert call_args[0]["cr_type"] == "inferenceservice"


def test_metrics_batch_endpoint_without_cr_type_defaults(isolated_client, monkeypatch):
    from services.shared import multi_target_collector

    call_args = []

    async def mock_get_metrics(namespace, is_name, cr_type=None):
        call_args.append({"namespace": namespace, "is_name": is_name, "cr_type": cr_type})
        return None

    monkeypatch.setattr(multi_target_collector, "get_metrics", mock_get_metrics)

    response = isolated_client.post(
        "/api/metrics/batch",
        json={"targets": [{"namespace": "test-ns", "inferenceService": "default-svc"}]},
    )
    assert response.status_code == 200
    data = response.json()

    assert "test-ns/default-svc/inferenceservice" in data["results"]
    assert len(call_args) >= 1
    assert call_args[0]["cr_type"] is None


def test_thanos_500_error(isolated_client):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Server Error",
        request=MagicMock(),
        response=MagicMock(status_code=500),
    )
    mock_cm = _make_async_client_mock(AsyncMock(return_value=mock_response))

    with patch("services.metrics_service.httpx.AsyncClient", return_value=mock_cm):
        response = isolated_client.post(
            "/api/metrics/batch",
            json={
                "targets": [{"namespace": "test-ns", "inferenceService": "test-isvc"}],
                "time_range": "1h",
            },
        )
    assert response.status_code == 200
    data = response.json()
    target_result = data["results"]["test-ns/test-isvc/inferenceservice"]
    assert target_result["history"] == []


def test_thanos_timeout(isolated_client):
    mock_cm = _make_async_client_mock(AsyncMock(side_effect=httpx.TimeoutException("timed out")))

    with patch("services.metrics_service.httpx.AsyncClient", return_value=mock_cm):
        response = isolated_client.post(
            "/api/metrics/batch",
            json={
                "targets": [{"namespace": "test-ns", "inferenceService": "test-isvc"}],
                "time_range": "1h",
            },
        )
    assert response.status_code == 200
    data = response.json()
    target_result = data["results"]["test-ns/test-isvc/inferenceservice"]
    assert target_result["history"] == []


def test_thanos_malformed_response(isolated_client):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"status": "success", "data": {}}
    mock_cm = _make_async_client_mock(AsyncMock(return_value=mock_response))

    with patch("services.metrics_service.httpx.AsyncClient", return_value=mock_cm):
        response = isolated_client.post(
            "/api/metrics/batch",
            json={
                "targets": [{"namespace": "test-ns", "inferenceService": "test-isvc"}],
                "time_range": "1h",
            },
        )
    assert response.status_code == 200
    data = response.json()
    target_result = data["results"]["test-ns/test-isvc/inferenceservice"]
    assert target_result["history"] == []


def test_fetch_query_range_thanos_500_returns_empty():
    from routers.metrics import _fetch_query_range

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock(status_code=500)
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = asyncio.run(_fetch_query_range(mock_client, {}, "test_metric{}", 0.0, 100.0, 10))
    assert result == []


def test_fetch_query_range_malformed_json_returns_empty():
    from routers.metrics import _fetch_query_range

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"status": "error", "error": "query failed"}
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = asyncio.run(_fetch_query_range(mock_client, {}, "test_metric{}", 0.0, 100.0, 10))
    assert result == []


def test_fetch_query_range_nan_inf_values_filtered():
    from routers.metrics import _fetch_query_range

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "status": "success",
        "data": {
            "result": [
                {
                    "values": [
                        [1000.0, "NaN"],
                        [1010.0, "Inf"],
                        [1020.0, "42.5"],
                    ]
                }
            ]
        },
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = asyncio.run(_fetch_query_range(mock_client, {}, "test_metric{}", 0.0, 100.0, 10))
    assert len(result) == 1
    assert result[0] == (1020.0, 42.5)


def test_batch_endpoint_invalid_time_range(isolated_client):
    """Invalid time_range (not in _TIME_RANGE_CONFIG) should skip Thanos and return local cache history."""
    response = isolated_client.post(
        "/api/metrics/batch",
        json={
            "targets": [{"namespace": "test-ns", "inferenceService": "test-isvc"}],
            "time_range": "999h",  # Invalid: not in config
        },
    )
    assert response.status_code == 200
    data = response.json()
    target_result = data["results"]["test-ns/test-isvc/inferenceservice"]
    assert "history" in target_result
    # With isolated_client and no prior metrics collection, history should be empty
    assert target_result["history"] == []


def test_batch_endpoint_null_time_range(isolated_client):
    """Null time_range should skip Thanos and return valid response with local cache history."""
    response = isolated_client.post(
        "/api/metrics/batch",
        json={
            "targets": [{"namespace": "test-ns", "inferenceService": "test-isvc"}],
            "time_range": None,  # Explicitly null
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "test-ns/test-isvc/inferenceservice" in data["results"]
    target_result = data["results"]["test-ns/test-isvc/inferenceservice"]
    assert "status" in target_result
    assert target_result["status"] in ("collecting", "ready")
    assert "history" in target_result
    # With isolated_client, history from local cache should be empty
    assert target_result["history"] == []


def test_metrics_batch_endpoint_mixed_isvc_and_llmisvc(isolated_client, monkeypatch):
    from services.shared import multi_target_collector

    call_args = []

    async def mock_get_metrics(namespace, is_name, cr_type=None):
        call_args.append({"namespace": namespace, "is_name": is_name, "cr_type": cr_type})
        return None

    monkeypatch.setattr(multi_target_collector, "get_metrics", mock_get_metrics)

    response = isolated_client.post(
        "/api/metrics/batch",
        json={
            "targets": [
                {"namespace": "ns-a", "inferenceService": "svc-isvc", "cr_type": "inferenceservice"},
                {"namespace": "ns-b", "inferenceService": "svc-llmis", "cr_type": "llminferenceservice"},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()

    assert "ns-a/svc-isvc/inferenceservice" in data["results"]
    assert "ns-b/svc-llmis/llminferenceservice" in data["results"]

    isvc_call = next(c for c in call_args if c["cr_type"] == "inferenceservice")
    llmis_call = next(c for c in call_args if c["cr_type"] == "llminferenceservice")

    assert isvc_call["namespace"] == "ns-a"
    assert isvc_call["is_name"] == "svc-isvc"
    assert llmis_call["namespace"] == "ns-b"
    assert llmis_call["is_name"] == "svc-llmis"
