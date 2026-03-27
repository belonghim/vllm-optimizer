import asyncio
import json
import time
from typing import cast
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from models.load_test import LoadTestConfig, TuningConfig


def _benchmark_payload() -> dict[str, object]:
    return {
        "name": "chaos-benchmark",
        "config": {
            "endpoint": "http://localhost:8000",
            "model": "qwen2-5-7b-instruct",
            "prompt_template": "Hello",
            "total_requests": 1,
            "concurrency": 1,
            "rps": 0,
            "max_tokens": 16,
            "temperature": 0.0,
            "stream": False,
        },
        "result": {
            "elapsed": 0.1,
            "total": 1,
            "success": 1,
            "failed": 0,
            "rps_actual": 1.0,
            "latency": {"mean": 0.1, "p50": 0.1, "p95": 0.1, "p99": 0.1, "min": 0.1, "max": 0.1},
            "ttft": {"mean": 0.01, "p50": 0.01, "p95": 0.01, "p99": 0.01, "min": 0.01, "max": 0.01},
            "tps": {"mean": 10.0, "total": 10.0},
        },
    }


def test_chaos_thanos_unavailable_returns_gracefully(isolated_client: TestClient):
    with patch("routers.metrics.multi_target_collector.get_metrics", new=AsyncMock(return_value=None)):
        response = isolated_client.get("/api/metrics/latest")

    assert response.status_code in (200, 204)
    assert response.status_code != 500
    if response.status_code == 200:
        body = cast(dict[str, object], response.json())
        assert body.get("tps") == 0.0
        assert body.get("latency_p99") == 0.0


def test_chaos_k8s_forbidden_tuner_sse_error(isolated_client: TestClient):
    event_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    async def _start_emit_rbac_error(
        config: TuningConfig,
        vllm_endpoint: str,
        auto_benchmark: bool = False,
        skip_preflight: bool = False,
    ) -> dict[str, object]:
        _ = (config, vllm_endpoint, auto_benchmark, skip_preflight)
        return {"error": "403 Forbidden", "error_type": "rbac"}

    preflight_mock = AsyncMock(return_value={"success": True})
    event_queue.put_nowait(
        {
            "type": "tuning_error",
            "data": {
                "error": "InferenceService 접근 권한이 없습니다 (403 Forbidden). Role/RoleBinding 설정을 확인하세요.",
                "error_type": "rbac",
            },
        }
    )
    event_queue.put_nowait({"type": "tuning_complete", "data": {"best_params": {}, "total_trials": 0}})

    with patch("routers.tuner.auto_tuner._preflight_check", new=preflight_mock):
        with patch("routers.tuner.auto_tuner.subscribe", new=AsyncMock(return_value=event_queue)):
            with patch("routers.tuner.auto_tuner.unsubscribe", new=AsyncMock(return_value=None)):
                with patch("routers.tuner.auto_tuner.start", new=AsyncMock(side_effect=_start_emit_rbac_error)):
                    start_resp = isolated_client.post(
                        "/api/tuner/start",
                        json={
                            "objective": "balanced",
                            "n_trials": 1,
                            "eval_requests": 2,
                            "vllm_endpoint": "http://mock-vllm:8080",
                        },
                    )
                    assert start_resp.status_code == 200

                    stream_response = isolated_client.get("/api/tuner/stream")
                    assert stream_response.status_code == 200
                    tuning_error_event: dict[str, object] | None = None
                    for line in stream_response.text.splitlines():
                        if not line.startswith("data: "):
                            continue
                        event = cast(dict[str, object], json.loads(line[6:]))
                        if event.get("type") == "tuning_error":
                            tuning_error_event = event
                            break

    assert tuning_error_event is not None
    event_data = cast(dict[str, object], tuning_error_event["data"])
    assert event_data.get("error_type") == "rbac"
    assert "403" in str(event_data.get("error", ""))


def test_chaos_vllm_timeout_load_engine_fails_gracefully(isolated_client: TestClient):
    async def _timeout_run(config: LoadTestConfig, skip_preflight: bool = False) -> dict[str, object]:
        _ = skip_preflight
        return {
            "success": False,
            "error": "vLLM request timed out",
            "error_type": "timeout",
            "failed": config.total_requests,
        }

    with patch("routers.load_test.load_engine.run", new=AsyncMock(side_effect=_timeout_run)):
        start_resp = isolated_client.post(
            "/api/load_test/start",
            json={
                "endpoint": "http://mock-vllm:8080",
                "model": "qwen2-5-7b-instruct",
                "total_requests": 3,
                "concurrency": 1,
                "rps": 0,
            },
        )
        assert start_resp.status_code == 200

        time.sleep(0.1)
        status_resp = isolated_client.get("/api/load_test/status")
        history_resp = isolated_client.get("/api/load_test/history?limit=1")

    assert status_resp.status_code == 200
    assert status_resp.json()["running"] is False
    assert history_resp.status_code == 200
    history = cast(list[dict[str, object]], history_resp.json())
    assert isinstance(history, list)
    assert len(history) >= 1
    latest_result = cast(dict[str, object], history[0].get("result", {}))
    failed_value = cast(int, latest_result.get("failed", 0))
    assert latest_result.get("error_type") == "timeout" or failed_value > 0


def test_chaos_storage_error_benchmark_fails_open(isolated_client: TestClient):
    from unittest.mock import MagicMock
    from routers.benchmark import get_storage

    mock_storage = MagicMock()
    mock_storage.save_benchmark = AsyncMock(side_effect=ValueError("sqlite unavailable"))
    isolated_client.app.dependency_overrides[get_storage] = lambda: mock_storage
    try:
        save_resp = isolated_client.post("/api/benchmark/save", json=_benchmark_payload())
    finally:
        del isolated_client.app.dependency_overrides[get_storage]

    assert save_resp.status_code in (500, 503)
    assert save_resp.status_code != 200

    follow_up = isolated_client.get("/api/metrics/latest")
    assert follow_up.status_code == 200
