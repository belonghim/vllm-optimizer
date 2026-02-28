import pytest
from fastapi.testclient import TestClient

from ..main import app
from ..models.load_test import LoadTestConfig, LoadTestResult, LatencyStats, TpsStats
from ..models.load_test import Benchmark


@pytest.fixture
def client():
    return TestClient(app)


def test_benchmark_list_empty(client):
    response = client.get("/api/benchmark/list")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


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
