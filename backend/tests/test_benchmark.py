import asyncio
import json
from typing import Any

import pytest


@pytest.fixture
def client(isolated_client, monkeypatch):
    from routers.benchmark import get_storage
    from services.storage import Storage

    test_storage = Storage(":memory:")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test_storage.initialize())

    isolated_client.app.dependency_overrides[get_storage] = lambda: test_storage

    yield isolated_client

    if get_storage in isolated_client.app.dependency_overrides:
        del isolated_client.app.dependency_overrides[get_storage]

    loop.run_until_complete(test_storage.close())
    loop.close()


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
        },
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
    client.post("/api/benchmark/save", json={**_BASE_PAYLOAD, "name": "run-A"})  # type: ignore  # dict spread type inference limitation
    payload_b = {**_BASE_PAYLOAD, "name": "run-B", "config": {**_BASE_PAYLOAD["config"], "model": "model-B"}}  # type: ignore  # dict spread type inference limitation
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
        **_BASE_PAYLOAD,  # type: ignore  # dict spread type inference limitation
        "result": {**_BASE_PAYLOAD["result"], "gpu_utilization_avg": 0.0},
    }
    client.post("/api/benchmark/save", json=payload)

    resp = client.get("/api/benchmark/by-model")
    assert resp.status_code == 200
    items = resp.json()["models"]["model-A"]
    assert items[0]["gpu_efficiency"] is None


_VALID_GUIDELLM = {
    "metadata": {"version": 1, "guidellm_version": "0.1.0"},
    "benchmarks": [
        {
            "config": {"target": "http://localhost:8000", "model": "test-model"},
            "metrics": {},
            "scheduler_metrics": {
                "requests_made": {
                    "total": 5,
                    "successful": 5,
                    "errored": 0,
                    "incomplete": 0,
                },
                "measure_start_time": 1000.0,
                "measure_end_time": 1002.0,
            },
        }
    ],
}


def test_import_guidellm_invalid_json(client):
    resp = client.post(
        "/api/benchmark/import",
        files={"file": ("test.json", b"not valid json!!!", "application/json")},
    )
    assert resp.status_code == 400


def test_import_guidellm_wrong_version(client):
    data = {
        "metadata": {"version": 99},
        "benchmarks": [{"config": {}, "metrics": {}, "scheduler_metrics": {}}],
    }
    resp = client.post(
        "/api/benchmark/import",
        files={"file": ("test.json", json.dumps(data).encode(), "application/json")},
    )
    assert resp.status_code == 422


def test_import_guidellm_empty_benchmarks(client):
    data = {"metadata": {"version": 1}, "benchmarks": []}
    resp = client.post(
        "/api/benchmark/import",
        files={"file": ("test.json", json.dumps(data).encode(), "application/json")},
    )
    assert resp.status_code == 422


def test_import_guidellm_valid(client):
    resp = client.post(
        "/api/benchmark/import",
        files={"file": ("test.json", json.dumps(_VALID_GUIDELLM).encode(), "application/json")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported_count"] == 1
    assert len(body["benchmark_ids"]) == 1


def test_patch_metadata_not_found(client):
    resp = client.patch("/api/benchmark/9999/metadata", json={"notes": "ghost"})
    assert resp.status_code == 404


def test_patch_metadata_valid(client):
    save_resp = client.post("/api/benchmark/save", json=_BASE_PAYLOAD)
    assert save_resp.status_code == 200
    bm_id = save_resp.json()["id"]

    patch_resp = client.patch(f"/api/benchmark/{bm_id}/metadata", json={"notes": "updated note"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["metadata"]["notes"] == "updated note"
