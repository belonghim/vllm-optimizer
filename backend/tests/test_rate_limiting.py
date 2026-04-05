from fastapi.testclient import TestClient

from ..models.load_test import LoadTestConfig


def test_load_test_start_rate_limited_after_5(isolated_client: TestClient):
    config = LoadTestConfig().model_dump()
    for i in range(5):
        resp = isolated_client.post("/api/load_test/start", json=config)
        assert resp.status_code != 429, f"Request {i + 1} should not be rate limited, got {resp.status_code}"
    resp = isolated_client.post("/api/load_test/start", json=config)
    assert resp.status_code == 429


def test_tuner_start_rate_limited_after_3(isolated_client: TestClient):
    body = {"objective": "balanced", "n_trials": 2, "vllm_endpoint": "http://vllm"}
    for i in range(3):
        resp = isolated_client.post("/api/tuner/start", json=body)
        assert resp.status_code != 429, f"Request {i + 1} should not be rate limited, got {resp.status_code}"
    resp = isolated_client.post("/api/tuner/start", json=body)
    assert resp.status_code == 429


def test_health_not_rate_limited(isolated_client: TestClient):
    for i in range(20):
        resp = isolated_client.get("/health")
        assert resp.status_code == 200, f"Request {i + 1} hit unexpected status {resp.status_code}"


def test_stream_not_rate_limited(isolated_client: TestClient):
    import asyncio
    from unittest.mock import AsyncMock, patch

    q: asyncio.Queue = asyncio.Queue()
    q.put_nowait({"type": "completed"})

    with (
        patch("services.load_engine.LoadTestEngine.subscribe", new=AsyncMock(return_value=q)),
        patch("services.load_engine.LoadTestEngine.unsubscribe", new=AsyncMock()),
    ):
        resp = isolated_client.get("/api/load_test/stream")

    assert resp.status_code != 429


def test_metrics_not_rate_limited(isolated_client: TestClient):
    for i in range(10):
        resp = isolated_client.get("/metrics")
        assert resp.status_code != 429, f"Request {i + 1} should not be rate limited"
