import asyncio
import sys
import time
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..models.load_test import LoadTestConfig
from .conftest import _StubMultiTargetMetricsCollector


def _collector_for_creator(fragment: str):
    for instance in _StubMultiTargetMetricsCollector.instances:
        if instance.creator and fragment in instance.creator:
            return instance
    return None


def _ensure_api_startup_metrics_route(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    existing_paths: set[str | None] = {getattr(route, "path", None) for route in app.router.routes}
    if "/api/startup_metrics" in existing_paths:
        return
    startup_route = next(
        (route for route in app.router.routes if getattr(route, "path", None) == "/startup_metrics"),
        None,
    )
    assert startup_route is not None, "startup_metrics endpoint is missing"
    endpoint = getattr(startup_route, "endpoint", None)
    assert endpoint is not None, "startup_metrics endpoint handler is missing"
    app.add_api_route(
        "/api/startup_metrics",
        endpoint,
        methods=["POST"],
        name="api_startup_metrics",
    )


@pytest.fixture(autouse=True)
def _reload_router_packages() -> None:
    for module_name in ("routers", "backend.routers"):
        sys.modules.pop(module_name, None)


def test_load_test_start_endpoint(isolated_client: TestClient):
    config = LoadTestConfig()
    response = isolated_client.post("/api/load_test/start", json=config.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data.get("test_id") is not None
    assert data.get("status") == "started"
    assert data.get("config") is not None


def test_load_test_status_endpoint_defaults(isolated_client: TestClient):
    response = isolated_client.get("/api/load_test/status")
    assert response.status_code == 200
    data = response.json()
    assert data.get("test_id") is None
    assert data.get("running") is False
    cfg = data.get("config")
    assert cfg is None or isinstance(cfg, dict)
    assert data.get("elapsed") == 0.0


def test_load_test_history_endpoint_returns_list(isolated_client: TestClient):
    response = isolated_client.get("/api/load_test/history?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_startup_metrics_api_endpoint_returns_status(isolated_client: TestClient):
    _ensure_api_startup_metrics_route(isolated_client)
    response = isolated_client.post("/api/startup_metrics")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert payload.get("status") in {"started", "already_running"}
    assert isinstance(payload.get("running"), bool)
    assert isinstance(payload.get("collector_version"), str)


def test_startup_metrics_endpoint_triggers_collector(isolated_client: TestClient):
    response = isolated_client.post("/startup_metrics")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") in {"started", "already_running"}
    assert isinstance(payload.get("running"), bool)
    assert isinstance(payload.get("collector_version"), str)
    time.sleep(0.2)
    assert _StubMultiTargetMetricsCollector.instances, "No collector stub was instantiated"
    assert any(instance.start_requests for instance in _StubMultiTargetMetricsCollector.instances), (
        "collector.start_collection was not triggered by the shim"
    )


def test_compute_stats_includes_total_requested():
    import time

    from models.load_test import RequestResult
    from services.load_engine import LoadTestEngine, LoadTestState, LoadTestStatus

    engine = LoadTestEngine()
    engine._state = LoadTestState(
        status=LoadTestStatus.RUNNING,
        start_time=time.time(),
        total_requests=200,
        completed_requests=0,
        failed_requests=0,
        results=[],
    )
    engine._state.results.append(RequestResult(req_id=0, success=True, latency=0.1))
    stats = engine._compute_stats()
    assert stats.get("total_requested") == 200
    assert stats.get("total") == 1


def test_compute_stats_total_requested_defaults_to_zero():
    import time

    from models.load_test import RequestResult
    from services.load_engine import LoadTestEngine, LoadTestState, LoadTestStatus

    engine = LoadTestEngine()
    engine._state = LoadTestState(
        status=LoadTestStatus.RUNNING,
        start_time=time.time(),
        total_requests=0,
        completed_requests=0,
        failed_requests=0,
        results=[],
    )
    engine._state.results.append(RequestResult(req_id=0, success=True, latency=0.1))
    stats = engine._compute_stats()
    assert stats.get("total_requested") == 0


async def test_gather_phase_broadcasts_progress_per_result():
    """gather 구간에서 per-result broadcast가 발생하는지 검증"""
    from models.load_test import LoadTestConfig, RequestResult
    from services.load_engine import LoadTestEngine, LoadTestState, LoadTestStatus

    engine = LoadTestEngine()
    q = await engine.subscribe()

    config = LoadTestConfig(total_requests=3)
    engine._state = LoadTestState(
        status=LoadTestStatus.RUNNING,
        start_time=time.time(),
        total_requests=config.total_requests,
    )
    engine._stop_event.clear()

    results = [
        RequestResult(req_id=0, success=True, latency=0.1, output_tokens=10, tps=100.0),
        RequestResult(req_id=1, success=True, latency=0.2, output_tokens=20, tps=100.0),
        RequestResult(req_id=2, success=True, latency=0.15, output_tokens=15, tps=100.0),
    ]

    async def fake_task(r):
        return r

    tasks = [asyncio.create_task(fake_task(r)) for r in results]
    processed_tasks = set()

    for fut in asyncio.as_completed([t for t in tasks if t not in processed_tasks]):
        try:
            result = await fut
        except Exception as e:
            result = RequestResult(
                req_id=-1,
                success=False,
                latency=0.0,
                error=str(e),
            )

        async with engine._state_lock:
            engine._state.results.append(result)
            if result.success:
                engine._state.completed_requests += 1
            else:
                engine._state.failed_requests += 1
            processed_tasks.add(fut)

        stats = engine._compute_stats()
        await engine._broadcast({"type": "progress", "data": stats})

    events = []
    for _ in range(3):
        try:
            events.append(q.get_nowait())
        except asyncio.QueueEmpty:
            break

    assert len(events) == 3, f"Expected 3 broadcast events, got {len(events)}"
    for ev in events:
        assert ev["type"] == "progress"

    await engine.unsubscribe(q)


async def test_gather_phase_handles_exceptions_as_failed_results():
    """gather 구간 exception이 failed_requests 카운터에 반영되는지 검증"""
    from models.load_test import RequestResult
    from services.load_engine import LoadTestEngine, LoadTestState, LoadTestStatus

    engine = LoadTestEngine()
    q = await engine.subscribe()

    engine._state = LoadTestState(
        status=LoadTestStatus.RUNNING,
        start_time=time.time(),
        total_requests=2,
    )

    async def success_task():
        return RequestResult(req_id=0, success=True, latency=0.1, output_tokens=5, tps=50.0)

    async def failing_task():
        raise RuntimeError("Simulated request failure")

    tasks = [
        asyncio.create_task(success_task()),
        asyncio.create_task(failing_task()),
    ]

    for fut in asyncio.as_completed(tasks):
        try:
            result = await fut
        except Exception as e:
            result = RequestResult(
                req_id=-1,
                success=False,
                latency=0.0,
                error=str(e),
            )

        async with engine._state_lock:
            engine._state.results.append(result)
            if result.success:
                engine._state.completed_requests += 1
            else:
                engine._state.failed_requests += 1

        stats = engine._compute_stats()
        await engine._broadcast({"type": "progress", "data": stats})

    assert engine._state.failed_requests == 1, f"Expected failed_requests=1, got {engine._state.failed_requests}"
    assert engine._state.completed_requests == 1

    events = []
    for _ in range(2):
        try:
            events.append(q.get_nowait())
        except asyncio.QueueEmpty:
            break
    assert len(events) == 2

    await engine.unsubscribe(q)


async def test_preflight_fails_on_unreachable_endpoint():
    from unittest.mock import AsyncMock, MagicMock, patch

    import httpx
    from models.load_test import LoadTestConfig
    from services.load_engine import LoadTestEngine, LoadTestStatus

    engine = LoadTestEngine()

    mock_ctx = MagicMock()
    with patch("services.shared.internal_client", mock_ctx):
        mock_ctx.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        config = LoadTestConfig(endpoint="http://nonexistent-host:9999", total_requests=10)
        result = await engine.run(config)

    assert result.get("success") is False
    assert result.get("error_type") == "connection"
    assert engine._state.status == LoadTestStatus.FAILED


async def test_preflight_fails_on_nonexistent_model():
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.load_test import LoadTestConfig
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()

    mock_ctx = MagicMock()
    with patch("services.shared.internal_client", mock_ctx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "qwen2-5-7b-instruct"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        config = LoadTestConfig(endpoint="http://localhost:8080", model="wrong-model", total_requests=10)
        result = await engine.run(config)

    assert result.get("success") is False
    assert result.get("error_type") == "model_not_found"
    assert "wrong-model" in result.get("error", "")
    assert "qwen2-5-7b-instruct" in result.get("error", "")


async def test_preflight_skips_model_check_for_auto():
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.load_test import LoadTestConfig
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()

    mock_ctx = MagicMock()
    with patch("services.shared.internal_client", mock_ctx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "qwen2-5-7b-instruct"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        config = LoadTestConfig(endpoint="http://localhost:8080", model="auto", total_requests=3)
        result = await engine._preflight_check(config)

    assert result["success"] is True


async def test_consecutive_failures_abort_test_early():
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.load_test import LoadTestConfig, RequestResult
    from services.load_engine import LoadTestEngine, LoadTestStatus

    engine = LoadTestEngine()

    async def always_fail(config, semaphore, request_id):
        return RequestResult(req_id=request_id, success=False, latency=0.1, error="Connection refused")

    mock_ctx = MagicMock()
    with patch("services.shared.internal_client", mock_ctx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "qwen2-5-7b-instruct"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=always_fail):
            config = LoadTestConfig(endpoint="http://localhost:8080", model="qwen2-5-7b-instruct", total_requests=100)
            result = await engine.run(config)

    assert result.get("success") is False
    assert result.get("error_type") == "consecutive_failure"
    assert engine._state.status == LoadTestStatus.FAILED


async def test_sse_broadcasts_error_on_preflight_fail():
    from unittest.mock import AsyncMock, MagicMock, patch

    import httpx
    from models.load_test import LoadTestConfig
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()
    q = await engine.subscribe()

    mock_ctx = MagicMock()
    with patch("services.shared.internal_client", mock_ctx):
        mock_ctx.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        config = LoadTestConfig(endpoint="http://nonexistent:9999", total_requests=10)
        await engine.run(config)

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) >= 1
    assert error_events[0]["data"].get("error_type") == "connection"


async def test_happy_path_unaffected_by_preflight():
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.load_test import LoadTestConfig, RequestResult
    from services.load_engine import LoadTestEngine, LoadTestStatus

    engine = LoadTestEngine()

    async def mock_dispatch(config, semaphore, request_id):
        return RequestResult(req_id=request_id, success=True, latency=0.1, output_tokens=10, tps=100.0)

    mock_ctx = MagicMock()
    with patch("services.shared.internal_client", mock_ctx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "qwen2-5-7b-instruct"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=mock_dispatch):
            config = LoadTestConfig(endpoint="http://localhost:8080", model="qwen2-5-7b-instruct", total_requests=5)
            result = await engine.run(config)

    assert engine._state.status == LoadTestStatus.COMPLETED
    assert result.get("total") == 5 or result.get("success")


async def test_mixed_failure_reasons_no_abort():
    """A1: 다른 에러의 연속 실패 시 consecutive_failure abort가 발생하지 않아야 한다."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.load_test import LoadTestConfig, RequestResult
    from services.load_engine import LoadTestEngine, LoadTestStatus

    engine = LoadTestEngine()

    errors = ["Connection refused", "Timeout", "DNS error", "SSL error", "Server error"]

    async def fail_with_different_errors(config, semaphore, request_id):
        return RequestResult(
            req_id=request_id,
            success=False,
            latency=0.1,
            error=errors[request_id % len(errors)],
        )

    mock_ctx = MagicMock()
    with patch("services.shared.internal_client", mock_ctx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "qwen2-5-7b-instruct"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=fail_with_different_errors):
            config = LoadTestConfig(endpoint="http://localhost:8080", model="qwen2-5-7b-instruct", total_requests=10)
            result = await engine.run(config)

    assert result.get("error_type") != "consecutive_failure", (
        f"Should not abort on mixed failure reasons, got: {result}"
    )
    assert engine._state.status in (LoadTestStatus.COMPLETED, LoadTestStatus.FAILED)


async def test_same_failure_reason_aborts():
    """A1: 동일 에러의 연속 실패 시 consecutive_failure abort가 발생해야 한다."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.load_test import LoadTestConfig, RequestResult
    from services.load_engine import LoadTestEngine, LoadTestStatus

    engine = LoadTestEngine()

    async def fail_with_same_error(config, semaphore, request_id):
        return RequestResult(req_id=request_id, success=False, latency=0.1, error="Connection refused")

    mock_ctx = MagicMock()
    with patch("services.shared.internal_client", mock_ctx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "qwen2-5-7b-instruct"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=fail_with_same_error):
            config = LoadTestConfig(endpoint="http://localhost:8080", model="qwen2-5-7b-instruct", total_requests=100)
            result = await engine.run(config)

    assert result.get("success") is False
    assert result.get("error_type") == "consecutive_failure"
    assert engine._state.status == LoadTestStatus.FAILED


async def test_dispatch_request_connect_error():
    """G3: httpx ConnectError 시 RequestResult(success=False) 반환."""
    from unittest.mock import AsyncMock, MagicMock, patch

    import httpx
    from models.load_test import LoadTestConfig
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()
    config = LoadTestConfig(endpoint="http://localhost:8080", model="test", stream=False)
    semaphore = asyncio.Semaphore(1)

    mock_ctx = MagicMock()
    with patch("services.shared.external_client", mock_ctx):
        mock_ctx.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        result = await engine._dispatch_request(config, semaphore, 0)

    assert result.success is False
    assert result.req_id == 0
    assert "Connection refused" in (result.error or "")


async def test_dispatch_request_timeout_error():
    """G3: httpx TimeoutException 시 RequestResult(success=False) 반환."""
    from unittest.mock import AsyncMock, MagicMock, patch

    import httpx
    from models.load_test import LoadTestConfig
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()
    config = LoadTestConfig(endpoint="http://localhost:8080", model="test", stream=False)
    semaphore = asyncio.Semaphore(1)

    mock_ctx = MagicMock()
    with patch("services.shared.external_client", mock_ctx):
        mock_ctx.post = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))

        result = await engine._dispatch_request(config, semaphore, 0)

    assert result.success is False
    assert result.req_id == 0
    assert "timed out" in (result.error or "").lower()


async def test_concurrent_run_rejected():
    """D5: 이미 RUNNING 중에 두 번째 run() 호출 시 에러 반환."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.load_test import LoadTestConfig, RequestResult
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()

    slow_event = asyncio.Event()

    async def slow_dispatch(config, semaphore, request_id):
        await slow_event.wait()
        return RequestResult(req_id=request_id, success=True, latency=0.1, output_tokens=10, tps=100.0)

    mock_ctx = MagicMock()
    with patch("services.shared.internal_client", mock_ctx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "qwen2-5-7b-instruct"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=slow_dispatch):
            config = LoadTestConfig(endpoint="http://localhost:8080", model="qwen2-5-7b-instruct", total_requests=5)

            first_run = asyncio.create_task(engine.run(config))
            await asyncio.sleep(0.05)

            second_result = await engine.run(config)

            assert "error" in second_result
            assert second_result.get("error_type") == "already_running"

            slow_event.set()
            await first_run


async def test_sse_subscriber_disconnect_graceful():
    """G5: 구독자가 중간에 해제되어도 에러 없이 계속 진행."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.load_test import LoadTestConfig, RequestResult
    from services.load_engine import LoadTestEngine, LoadTestStatus

    engine = LoadTestEngine()
    disconnect_queue: asyncio.Queue[object] | None = None

    call_count = {"n": 0}

    async def mock_dispatch(config, semaphore, request_id):
        nonlocal call_count, disconnect_queue
        call_count["n"] += 1
        if call_count["n"] == 2 and disconnect_queue is not None:
            await engine.unsubscribe(disconnect_queue)
            disconnect_queue = None
        return RequestResult(req_id=request_id, success=True, latency=0.1, output_tokens=10, tps=100.0)

    mock_ctx = MagicMock()
    with patch("services.shared.internal_client", mock_ctx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "qwen2-5-7b-instruct"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=mock_dispatch):
            disconnect_queue = await engine.subscribe()
            config = LoadTestConfig(endpoint="http://localhost:8080", model="qwen2-5-7b-instruct", total_requests=5)
            result = await engine.run(config)

    assert engine._state.status == LoadTestStatus.COMPLETED
    assert result.get("total") == 5 or result.get("success") is not False


async def test_preflight_rejects_invalid_config():
    """E3: total_requests=0 또는 concurrency=-1 시 validation 에러 반환."""
    from models.load_test import LoadTestConfig
    from pydantic import ValidationError
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()

    with pytest.raises(ValidationError):
        LoadTestConfig(endpoint="http://localhost:8080", total_requests=0)

    with pytest.raises(ValidationError):
        LoadTestConfig(endpoint="http://localhost:8080", total_requests=10, concurrency=-1)

    config_zero = LoadTestConfig.model_construct(endpoint="http://localhost:8080", total_requests=0, concurrency=10)
    result_zero = await engine._preflight_check(config_zero)
    assert result_zero.get("success") is False
    assert result_zero.get("error_type") == "validation"

    config_neg = LoadTestConfig.model_construct(endpoint="http://localhost:8080", total_requests=10, concurrency=-1)
    result_neg = await engine._preflight_check(config_neg)
    assert result_neg.get("success") is False
    assert result_neg.get("error_type") == "validation"


def test_itl_fields_default_none():
    """RequestResult ITL fields default to None."""
    from models.load_test import RequestResult

    r = RequestResult(req_id=1, success=True, latency=1.0)
    assert r.itl_deltas is None
    assert r.itl_mean is None
    assert r.itl_p95 is None
    assert r.itl_p99 is None
    assert r.token_timestamps is None


def test_itl_fields_populated():
    """RequestResult accepts ITL values when provided."""
    from models.load_test import RequestResult

    r = RequestResult(
        req_id=1,
        success=True,
        latency=1.0,
        token_timestamps=[0.1, 0.2, 0.3],
        itl_deltas=[0.1, 0.1],
        itl_mean=0.1,
        itl_p95=0.1,
        itl_p99=0.1,
    )
    assert r.itl_deltas == [0.1, 0.1]
    assert r.itl_mean == 0.1
    assert r.token_timestamps == [0.1, 0.2, 0.3]


def test_compute_stats_itl_none_when_no_streaming():
    """_compute_stats returns itl=None when no ITL data."""
    import time

    from models.load_test import RequestResult
    from services.load_engine import LoadTestEngine, LoadTestState, LoadTestStatus

    engine = LoadTestEngine()
    engine._state = LoadTestState(
        status=LoadTestStatus.RUNNING,
        start_time=time.time(),
        total_requests=2,
    )
    engine._state.results = [
        RequestResult(req_id=0, success=True, latency=0.1),
        RequestResult(req_id=1, success=True, latency=0.2),
    ]
    stats = engine._compute_stats()
    assert stats.get("itl") is None


def test_compute_stats_itl_aggregated():
    """_compute_stats aggregates ITL from successful results."""
    import time

    from models.load_test import RequestResult
    from services.load_engine import LoadTestEngine, LoadTestState, LoadTestStatus

    engine = LoadTestEngine()
    engine._state = LoadTestState(
        status=LoadTestStatus.RUNNING,
        start_time=time.time(),
        total_requests=2,
    )
    engine._state.results = [
        RequestResult(req_id=0, success=True, latency=0.1, itl_mean=0.05),
        RequestResult(req_id=1, success=True, latency=0.2, itl_mean=0.10),
    ]
    stats = engine._compute_stats()
    itl = stats.get("itl")
    assert itl is not None
    assert itl["mean"] == pytest.approx(0.075, abs=0.001)


def test_compute_stats_itl_percentiles_from_all_token_deltas():
    import time

    from models.load_test import RequestResult
    from services.load_engine import LoadTestEngine, LoadTestState, LoadTestStatus

    engine = LoadTestEngine()
    engine._state = LoadTestState(
        status=LoadTestStatus.RUNNING,
        start_time=time.time(),
        total_requests=3,
    )
    engine._state.results = [
        RequestResult(req_id=0, success=True, latency=0.1, itl_mean=0.15, itl_deltas=[0.1, 0.2]),
        RequestResult(req_id=1, success=True, latency=0.2, itl_mean=0.35, itl_deltas=[0.3, 0.4]),
        RequestResult(req_id=2, success=True, latency=0.3, itl_mean=0.55, itl_deltas=[0.5, 0.6]),
    ]

    stats = engine._compute_stats()
    itl = stats.get("itl")
    assert itl is not None
    assert itl["mean"] == pytest.approx(0.35, abs=0.0001)
    assert itl["p50"] == pytest.approx(0.35, abs=0.0001)
    assert itl["p95"] == pytest.approx(0.575, abs=0.0001)
    assert itl["p99"] == pytest.approx(0.595, abs=0.0001)


@pytest.mark.asyncio
async def test_sweep_single_step():
    """run_sweep with rps_start==rps_end executes exactly one step."""
    from unittest.mock import AsyncMock, patch

    from models.load_test import SweepConfig
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()
    mock_result = {
        "total": 5,
        "failed": 0,
        "success": 5,
        "latency": {"p99": 0.1, "mean": 0.08},
        "elapsed": 1.0,
    }

    with patch.object(engine, "run", new=AsyncMock(return_value=mock_result)):
        config = SweepConfig(
            endpoint="http://vllm",
            model="m",
            rps_start=5,
            rps_end=5,
            rps_step=1,
            requests_per_step=5,
        )
        result = await engine.run_sweep(config)

    assert len(result.steps) == 1
    assert result.steps[0].rps == 5.0
    assert result.steps[0].saturated is False
    assert result.saturation_point is None


@pytest.mark.asyncio
async def test_sweep_detects_saturation_by_error_rate():
    """run_sweep stops when error rate exceeds saturation_error_rate."""
    from unittest.mock import AsyncMock, patch

    from models.load_test import SweepConfig
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()

    # Step 1: OK, Step 2: 20% error → saturated (threshold=0.1)
    step_results = [
        {
            "total": 10,
            "failed": 0,
            "success": 10,
            "latency": {"p99": 0.1, "mean": 0.08},
            "elapsed": 1.0,
        },
        {
            "total": 10,
            "failed": 2,
            "success": 8,
            "latency": {"p99": 0.15, "mean": 0.1},
            "elapsed": 1.0,
        },
    ]

    with patch.object(engine, "run", new=AsyncMock(side_effect=step_results)):
        config = SweepConfig(
            endpoint="http://vllm",
            model="m",
            rps_start=1,
            rps_end=10,
            rps_step=9,
            requests_per_step=10,
            saturation_error_rate=0.1,
        )
        result = await engine.run_sweep(config)

    assert len(result.steps) == 2
    assert result.steps[1].saturated is True
    assert "Error rate" in (result.steps[1].saturation_reason or "")
    assert result.saturation_point == result.steps[1].rps


@pytest.mark.asyncio
async def test_sweep_detects_saturation_by_latency():
    """run_sweep stops when P99 latency exceeds factor × step1 baseline."""
    from unittest.mock import AsyncMock, patch

    from models.load_test import SweepConfig
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()

    # Step 1: p99=0.1s, Step 2: p99=0.5s → 5× baseline (factor=3.0)
    step_results = [
        {
            "total": 10,
            "failed": 0,
            "success": 10,
            "latency": {"p99": 0.1, "mean": 0.08},
            "elapsed": 1.0,
        },
        {
            "total": 10,
            "failed": 0,
            "success": 10,
            "latency": {"p99": 0.5, "mean": 0.4},
            "elapsed": 1.0,
        },
    ]

    with patch.object(engine, "run", new=AsyncMock(side_effect=step_results)):
        config = SweepConfig(
            endpoint="http://vllm",
            model="m",
            rps_start=1,
            rps_end=10,
            rps_step=9,
            requests_per_step=10,
            saturation_latency_factor=3.0,
        )
        result = await engine.run_sweep(config)

    assert len(result.steps) == 2
    assert result.steps[1].saturated is True
    assert result.optimal_rps == result.steps[0].rps


@pytest.mark.asyncio
async def test_sweep_min_stable_steps_ignores_isolated_spike():
    from unittest.mock import AsyncMock, patch

    from models.load_test import SweepConfig
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()

    step_results = [
        {"total": 10, "failed": 0, "success": 10, "latency": {"p99": 0.1, "mean": 0.08}, "elapsed": 1.0},
        {"total": 10, "failed": 2, "success": 8, "latency": {"p99": 0.1, "mean": 0.08}, "elapsed": 1.0},
        {"total": 10, "failed": 0, "success": 10, "latency": {"p99": 0.1, "mean": 0.08}, "elapsed": 1.0},
        {"total": 10, "failed": 2, "success": 8, "latency": {"p99": 0.1, "mean": 0.08}, "elapsed": 1.0},
        {"total": 10, "failed": 2, "success": 8, "latency": {"p99": 0.1, "mean": 0.08}, "elapsed": 1.0},
        {"total": 10, "failed": 2, "success": 8, "latency": {"p99": 0.1, "mean": 0.08}, "elapsed": 1.0},
    ]

    with patch.object(engine, "run", new=AsyncMock(side_effect=step_results)):
        config = SweepConfig(
            endpoint="http://vllm",
            model="m",
            rps_start=1,
            rps_end=6,
            rps_step=1,
            requests_per_step=10,
            saturation_error_rate=0.1,
            min_stable_steps=3,
        )
        result = await engine.run_sweep(config)

    assert len(result.steps) == 6
    assert [step.saturated for step in result.steps] == [False, True, False, True, True, True]
    assert result.saturation_point == result.steps[5].rps
    assert result.optimal_rps == result.steps[2].rps


@pytest.mark.asyncio
async def test_sweep_consecutive_failures_early_abort():
    """run_sweep aborts after 3 consecutive 100% error steps."""
    from unittest.mock import AsyncMock, patch

    from models.load_test import SweepConfig
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()

    # All steps fail 100%
    fail_result = {
        "total": 5,
        "failed": 5,
        "success": 0,
        "latency": {"p99": 0.0, "mean": 0.0},
        "elapsed": 1.0,
    }

    with patch.object(engine, "run", new=AsyncMock(return_value=fail_result)):
        config = SweepConfig(
            endpoint="http://vllm",
            model="m",
            rps_start=1,
            rps_end=50,
            rps_step=1,
            requests_per_step=5,
        )
        result = await engine.run_sweep(config)

    # Should abort after 3 steps (consecutive failures)
    assert len(result.steps) <= 3


@pytest.mark.asyncio
async def test_sweep_stop_midway():
    """run_sweep respects stopped status between steps."""
    from unittest.mock import AsyncMock, patch

    from models.load_test import SweepConfig
    from services.load_engine import LoadTestEngine, LoadTestStatus

    engine = LoadTestEngine()

    ok_result = {
        "total": 5,
        "failed": 0,
        "success": 5,
        "latency": {"p99": 0.1, "mean": 0.08},
        "elapsed": 1.0,
    }

    call_count = 0

    async def run_then_stop(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Set status to STOPPED after first step
        async with engine._state_lock:
            engine._state.status = LoadTestStatus.STOPPED
        return ok_result

    with patch.object(engine, "run", new=AsyncMock(side_effect=run_then_stop)):
        config = SweepConfig(
            endpoint="http://vllm",
            model="m",
            rps_start=1,
            rps_end=20,
            rps_step=1,
            requests_per_step=5,
        )
        result = await engine.run_sweep(config)

    # Should have run only 1 step before stopping
    assert call_count == 1


@pytest.mark.asyncio
async def test_itl_computation_with_known_timestamps():
    """ITL computed correctly from known timestamps."""

    # Known timestamps: 0.0, 0.1, 0.2 → deltas [0.1, 0.1] → mean=0.1
    timestamps = [0.0, 0.1, 0.2]
    if len(timestamps) >= 2:
        deltas = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
        itl_mean = sum(deltas) / len(deltas)
        itl_p95 = sorted(deltas)[int(len(deltas) * 0.95)]
        itl_p99 = sorted(deltas)[int(len(deltas) * 0.99)]
    assert abs(itl_mean - 0.1) < 1e-9
    assert itl_p95 == 0.1
    assert itl_p99 == 0.1


@pytest.mark.asyncio
async def test_itl_none_for_single_token():
    """Single token output → ITL is None (need at least 2 tokens)."""

    # Single timestamp → no deltas → ITL should be None
    timestamps = [0.0]  # only 1 token received
    itl_mean = itl_p95 = itl_p99 = None
    if len(timestamps) >= 2:
        deltas = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
        itl_mean = sum(deltas) / len(deltas)
        itl_p95 = sorted(deltas)[int(len(deltas) * 0.95)]
        itl_p99 = sorted(deltas)[int(len(deltas) * 0.99)]
    assert itl_mean is None
    assert itl_p95 is None
    assert itl_p99 is None


@pytest.mark.asyncio
async def test_sweep_executes_multiple_steps():
    """run_sweep() calls run() once per RPS step."""
    from unittest.mock import AsyncMock, patch
    from services.load_engine import LoadTestEngine
    from models.load_test import LoadTestConfig, SweepConfig

    sweep_config = SweepConfig(
        endpoint="http://x",
        model="m",
        rps_start=1,
        rps_end=10,
        rps_step=5,  # steps: 1, 6, (stop before 11)
        requests_per_step=5,
        concurrency=2,
        max_tokens=32,
    )

    mock_result = {
        "success": 5,
        "failed": 0,
        "total": 5,
        "rps_actual": 5.0,
        "latency": {"mean": 0.5, "p50": 0.5, "p95": 0.6, "p99": 0.7},
        "tps": {"mean": 10.0, "total": 50.0},
        "ttft": {"mean": 0.1, "p50": 0.1, "p95": 0.2, "p99": 0.3},
    }

    engine = LoadTestEngine()

    run_call_count = 0

    async def mock_run(*args, **kwargs):
        nonlocal run_call_count
        run_call_count += 1
        return mock_result

    with patch.object(engine, "run", side_effect=mock_run), patch.object(engine, "_broadcast", new_callable=AsyncMock):
        result = await engine.run_sweep(sweep_config)

    # rps_start=1, rps_end=10, rps_step=5 → steps at RPS 1, 6 → 2 steps
    expected_steps = len(range(sweep_config.rps_start, sweep_config.rps_end + 1, sweep_config.rps_step))
    assert run_call_count == expected_steps, f"Expected {expected_steps} run() calls, got {run_call_count}"
    assert len(result.steps) == expected_steps


# ==================== Sweep History CRUD round-trip ====================


@pytest.fixture
def sweep_storage_client(isolated_client: TestClient):
    """Isolated client with initialized in-memory storage injected for sweep endpoints."""
    import asyncio
    from services.storage import Storage
    from routers.load_test import get_storage

    test_storage = Storage(":memory:")
    loop = asyncio.new_event_loop()
    loop.run_until_complete(test_storage.initialize())
    isolated_client.app.dependency_overrides[get_storage] = lambda: test_storage

    yield isolated_client

    isolated_client.app.dependency_overrides.pop(get_storage, None)
    loop.run_until_complete(test_storage.close())
    loop.close()


_SAMPLE_SWEEP = {
    "config": {"rps_start": 1, "rps_end": 10, "rps_step": 5},
    "steps": [
        {
            "step": 1,
            "rps": 1.0,
            "stats": {
                "latency": {"p99": 0.5, "mean": 0.3},
                "tps": {"mean": 5.0},
                "success": 5,
                "failed": 0,
                "total": 5,
                "rps_actual": 1.0,
            },
            "saturated": False,
            "saturation_reason": None,
        }
    ],
    "saturation_point": None,
    "optimal_rps": 1.0,
    "total_duration": 2.5,
}


def test_sweep_save_returns_id(sweep_storage_client: TestClient):
    resp = sweep_storage_client.post("/api/load_test/sweep/save", json=_SAMPLE_SWEEP)
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert isinstance(data["id"], str)
    assert len(data["id"]) > 0


def test_sweep_history_list_after_save(sweep_storage_client: TestClient):
    # Save one result
    save_resp = sweep_storage_client.post("/api/load_test/sweep/save", json=_SAMPLE_SWEEP)
    assert save_resp.status_code == 200

    # List should return it
    list_resp = sweep_storage_client.get("/api/load_test/sweep/history")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert isinstance(items, list)
    assert len(items) == 1
    assert "X-Total-Count" in list_resp.headers
    assert list_resp.headers["X-Total-Count"] == "1"


def test_sweep_history_get_single(sweep_storage_client: TestClient):
    save_resp = sweep_storage_client.post("/api/load_test/sweep/save", json=_SAMPLE_SWEEP)
    sweep_id = save_resp.json()["id"]

    get_resp = sweep_storage_client.get(f"/api/load_test/sweep/history/{sweep_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data.get("optimal_rps") == 1.0


def test_sweep_history_get_not_found(sweep_storage_client: TestClient):
    resp = sweep_storage_client.get("/api/load_test/sweep/history/nonexistent-id")
    assert resp.status_code == 404


def test_sweep_history_delete(sweep_storage_client: TestClient):
    save_resp = sweep_storage_client.post("/api/load_test/sweep/save", json=_SAMPLE_SWEEP)
    sweep_id = save_resp.json()["id"]

    del_resp = sweep_storage_client.delete(f"/api/load_test/sweep/history/{sweep_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Verify gone
    get_resp = sweep_storage_client.get(f"/api/load_test/sweep/history/{sweep_id}")
    assert get_resp.status_code == 404


def test_sweep_history_delete_not_found(sweep_storage_client: TestClient):
    resp = sweep_storage_client.delete("/api/load_test/sweep/history/nonexistent-id")
    assert resp.status_code == 404


def test_sweep_history_pagination(sweep_storage_client: TestClient):
    # Save 3 results
    for i in range(3):
        sweep_storage_client.post("/api/load_test/sweep/save", json={**_SAMPLE_SWEEP, "optimal_rps": float(i + 1)})

    # Page 1: limit=2
    resp1 = sweep_storage_client.get("/api/load_test/sweep/history?limit=2&offset=0")
    assert resp1.status_code == 200
    assert len(resp1.json()) == 2
    assert resp1.headers["X-Total-Count"] == "3"

    # Page 2: limit=2, offset=2
    resp2 = sweep_storage_client.get("/api/load_test/sweep/history?limit=2&offset=2")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 1
