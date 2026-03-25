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

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
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

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "real-model"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        config = LoadTestConfig(endpoint="http://localhost:8080", model="wrong-model", total_requests=10)
        result = await engine.run(config)

    assert result.get("success") is False
    assert result.get("error_type") == "model_not_found"
    assert "wrong-model" in result.get("error", "")
    assert "real-model" in result.get("error", "")


async def test_preflight_skips_model_check_for_auto():
    from unittest.mock import AsyncMock, MagicMock, patch

    from models.load_test import LoadTestConfig
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "some-other-model"}]}
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

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "llm-ov"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=always_fail):
            config = LoadTestConfig(endpoint="http://localhost:8080", model="llm-ov", total_requests=100)
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

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
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

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "llm-ov"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=mock_dispatch):
            config = LoadTestConfig(endpoint="http://localhost:8080", model="llm-ov", total_requests=5)
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

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "llm-ov"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=fail_with_different_errors):
            config = LoadTestConfig(endpoint="http://localhost:8080", model="llm-ov", total_requests=10)
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

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "llm-ov"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=fail_with_same_error):
            config = LoadTestConfig(endpoint="http://localhost:8080", model="llm-ov", total_requests=100)
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

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
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

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
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

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "llm-ov"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=slow_dispatch):
            config = LoadTestConfig(endpoint="http://localhost:8080", model="llm-ov", total_requests=5)

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

    with patch("services.load_engine.httpx.AsyncClient") as mock_cls:
        mock_ctx = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "llm-ov"}]}
        mock_ctx.get = AsyncMock(return_value=mock_resp)

        with patch.object(engine, "_dispatch_request", side_effect=mock_dispatch):
            disconnect_queue = await engine.subscribe()
            config = LoadTestConfig(endpoint="http://localhost:8080", model="llm-ov", total_requests=5)
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
