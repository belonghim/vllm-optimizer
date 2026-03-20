import pytest
from fastapi.testclient import TestClient
from typing import Any
import asyncio
import sys


@pytest.fixture(autouse=True)
def setup_test_storage(monkeypatch):
    """Setup in-memory storage for each test."""
    from services.storage import Storage
    from services import shared

    test_storage = Storage(":memory:")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test_storage.initialize())

    monkeypatch.setattr(shared, "storage", test_storage)

    benchmark_module = sys.modules.get("routers.benchmark")
    if benchmark_module is not None:
        monkeypatch.setattr(benchmark_module, "storage", test_storage)

    yield test_storage

    loop.run_until_complete(test_storage.close())
    loop.close()


@pytest.fixture
def client():
    """Create test client."""
    from main import app
    return TestClient(app)


def test_benchmark_list_empty(client):
    response = client.get("/api/benchmark/list")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_benchmark_save_get_and_delete_in_one(client):
    payload = {
        "name": "test-run-1",
        "config": {
            "endpoint": "http://localhost:8000",
            "model": "auto",
            "prompt_template": "Hello",
            "total_requests": 1,
            "concurrency": 1,
            "rps": 0,
            "max_tokens": 64,
            "temperature": 0.5,
            "stream": False,
        },
        "result": {
            "elapsed": 0.1,
            "total": 1,
            "success": 1,
            "failed": 0,
            "rps_actual": 0.0,
            "latency": {"mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0},
            "ttft": {"mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0},
            "tps": {"mean": 0.0, "total": 0.0},
        }
    }
    resp = client.post("/api/benchmark/save", json=payload)
    assert resp.status_code == 200
    saved = resp.json()
    assert saved.get("id") == 1

    resp2 = client.get("/api/benchmark/1")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2.get("name") == payload["name"]

    resp3 = client.delete("/api/benchmark/1")
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3.get("status") == "deleted"


_BASE_PAYLOAD: dict[str, Any] = {
    "name": "test",
    "config": {
        "endpoint": "http://fake:8080",
        "model": "model-A",
        "total_requests": 10,
        "concurrency": 1,
    },
    "result": {
        "elapsed": 0.1,
        "total": 10,
        "success": 10,
        "failed": 0,
        "rps_actual": 1.0,
        "latency": {"mean": 0.1, "p50": 0.1, "p95": 0.2, "p99": 0.3, "min": 0.05, "max": 0.5},
        "ttft": {"mean": 0.05, "p50": 0.05, "p95": 0.08, "p99": 0.1, "min": 0.01, "max": 0.2},
        "tps": {"mean": 100.0, "total": 1000.0},
        "gpu_utilization_avg": 50.0,
    },
}


def test_by_model_empty(client):
    resp = client.get("/api/benchmark/by-model")
    assert resp.status_code == 200
    assert resp.json() == {"models": {}}


def test_by_model_grouping(client):
    client.post("/api/benchmark/save", json={**_BASE_PAYLOAD, "name": "run-A"})  # type: ignore
    payload_b = {**_BASE_PAYLOAD, "name": "run-B", "config": {**_BASE_PAYLOAD["config"], "model": "model-B"}}  # type: ignore
    client.post("/api/benchmark/save", json=payload_b)

    resp = client.get("/api/benchmark/by-model")
    assert resp.status_code == 200
    data = resp.json()
    assert "model-A" in data["models"]
    assert "model-B" in data["models"]


def test_by_model_gpu_efficiency(client):
    client.post("/api/benchmark/save", json=_BASE_PAYLOAD)

    resp = client.get("/api/benchmark/by-model")
    assert resp.status_code == 200
    items = resp.json()["models"]["model-A"]
    assert len(items) == 1
    assert abs(items[0]["gpu_efficiency"] - 2.0) < 0.001


def test_by_model_gpu_zero(client):
    payload = {
        **_BASE_PAYLOAD,  # type: ignore
        "result": {**_BASE_PAYLOAD["result"], "gpu_utilization_avg": 0.0},
    }
    client.post("/api/benchmark/save", json=payload)

    resp = client.get("/api/benchmark/by-model")
    assert resp.status_code == 200
    items = resp.json()["models"]["model-A"]
    assert items[0]["gpu_efficiency"] is None
