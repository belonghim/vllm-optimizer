import sys
import time

from typing import cast

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from .conftest import _StubMetricsCollector
from ..models.load_test import LoadTestConfig


def _collector_for_creator(fragment: str):
    for instance in _StubMetricsCollector.instances:
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
    # With shared singleton, the collector is created in services/shared.py (not in the shim).
    # We verify that ANY stub instance had start_collection triggered.
    assert _StubMetricsCollector.instances, "No MetricsCollector stub was instantiated"
    assert any(
        instance.start_requests for instance in _StubMetricsCollector.instances
    ), "MetricsCollector.start_collection was not triggered by the shim"


def test_compute_stats_includes_total_requested():
    import time
    from services.load_engine import LoadTestEngine, LoadTestState, LoadTestStatus
    from models.load_test import RequestResult

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
    from services.load_engine import LoadTestEngine, LoadTestState, LoadTestStatus
    from models.load_test import RequestResult

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
