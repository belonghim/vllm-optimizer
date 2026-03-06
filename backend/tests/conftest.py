"""
Pytest configuration and shared fixtures for backend tests.

This module provides minimal fixtures to enable test discovery without
requiring heavy dependencies or external services.
"""

import importlib
import inspect
import os
import sys
import types
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# Add the 'backend' directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


_MODULES_TO_CLEAR = [
    "backend.main",
    "backend.metrics.prometheus_metrics",
    "metrics.prometheus_metrics",
    "backend.services.load_engine",
    "services.load_engine",
    "backend.services.metrics_collector",
    "services.metrics_collector",
    "backend.services.auto_tuner",
    "services.auto_tuner",
    "backend.routers.load_test",
    "routers.load_test",
    "backend.routers.metrics",
    "routers.metrics",
    "backend.routers.benchmark",
    "routers.benchmark",
    "backend.routers.tuner",
    "routers.tuner",
    "startup_metrics_shim",
    "backend.startup_metrics_shim",
]


def _noop(*args: Any, **kwargs: Any) -> None:
    return None

class _StubMetricsCollector:

    """Lightweight stand-in for the real collector."""

    instances: list["_StubMetricsCollector"] = []

    def __init__(self):
        self.start_collection_calls: list[float] = []
        self.start_requests: list[float] = []
        self.stop_called: bool = False
        self.version: str = "stub"
        self.missing_metrics: list[str] = []
        self._history: list[dict[str, Any]] = []
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        self.creator: str | None = module.__name__ if module else None
        _StubMetricsCollector.instances.append(self)

    async def start_collection(self, interval: float = 2.0):
        self.start_collection_calls.append(interval)

    def record_start_request(self, interval: float):
        self.start_requests.append(interval)

    def stop(self):
        self.stop_called = True

    async def _detect_version(self) -> str:
        return "0.11.x"

    async def _query_prometheus(self) -> dict[str, float]:
        return {}

    def _query_kubernetes(self) -> dict[str, int]:
        return {"pod_count": 0, "pod_ready": 0}

    def get_history_dict(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return list(self._history)

    @property
    def latest(self):
        return None

    @classmethod
    def clear_instances(cls):
        cls.instances.clear()


class _DummyV1Deployment:
    pass


class _DummyK8sApi:
    def list_namespaced_pod(self, *args: Any, **kwargs: Any) -> types.SimpleNamespace:
        return types.SimpleNamespace(items=[])

    def read_namespaced_deployment(self, *args: Any, **kwargs: Any) -> types.SimpleNamespace:
        return types.SimpleNamespace(spec=types.SimpleNamespace(replicas=0))

    def read_namespaced_config_map(self, *args: Any, **kwargs: Any) -> types.SimpleNamespace:
        return types.SimpleNamespace(data={})

    def patch_namespaced_config_map(self, *args: Any, **kwargs: Any) -> types.SimpleNamespace:
        return types.SimpleNamespace()


class _DummyCustomObjectsApi:
    async def get_namespaced_custom_object(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": {"conditions": []}}

    async def patch_namespaced_custom_object(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}


def _ensure_kubernetes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Create stub modules and patch kube client/exported helpers."""

    kubernetes_module = sys.modules.get("kubernetes")
    if kubernetes_module is None:
        kubernetes_module = types.ModuleType("kubernetes")
        sys.modules["kubernetes"] = kubernetes_module
    kubernetes_module = cast(Any, kubernetes_module)

    config_module = sys.modules.get("kubernetes.config")
    if config_module is None:
        config_module = types.ModuleType("kubernetes.config")
        sys.modules["kubernetes.config"] = config_module

    client_module = sys.modules.get("kubernetes.client")
    if client_module is None:
        client_module = types.ModuleType("kubernetes.client")
        sys.modules["kubernetes.client"] = client_module

    kubernetes_module.config = config_module
    kubernetes_module.client = client_module

    for attr in ("load_incluster_config", "load_kube_config"):
        monkeypatch.setattr(config_module, attr, _noop, raising=False)

    monkeypatch.setattr(client_module, "CoreV1Api", _DummyK8sApi, raising=False)
    monkeypatch.setattr(client_module, "AppsV1Api", _DummyK8sApi, raising=False)
    monkeypatch.setattr(client_module, "CustomObjectsApi", _DummyCustomObjectsApi, raising=False)
    monkeypatch.setattr(client_module, "V1Deployment", _DummyV1Deployment, raising=False)


def _clear_modules() -> None:
    for module_name in _MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def _install_stub_metrics_collector_modules() -> list[str]:
    injected_names: list[str] = []
    for module_name in ("services.metrics_collector", "backend.services.metrics_collector"):
        stub_module = types.ModuleType(module_name)
        stub_any = cast(Any, stub_module)
        stub_any.MetricsCollector = _StubMetricsCollector
        stub_any.__all__ = ["MetricsCollector"]
        sys.modules[module_name] = stub_module
        injected_names.append(module_name)
    return injected_names


def _mock_update_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    for module_name in ("metrics.prometheus_metrics", "backend.metrics.prometheus_metrics"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        monkeypatch.setattr(module, "update_metrics", lambda *args, **kwargs: None, raising=False)


def _reload_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    main_module = importlib.import_module("backend.main")
    app: FastAPI = importlib.reload(main_module).app

    load_engine_module = importlib.import_module("services.load_engine")

    async def _stub_run(self: Any, config: Any) -> dict[str, Any]:
        self._state = load_engine_module.LoadTestState()
        self._state.status = load_engine_module.LoadTestStatus.COMPLETED
        return {}

    monkeypatch.setattr(
        "services.load_engine.LoadTestEngine.run",
        _stub_run,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.services.load_engine.LoadTestEngine.run",
        _stub_run,
        raising=False,
    )

    load_engine_module.load_engine._state = load_engine_module.LoadTestState()

    load_test_module = importlib.import_module("routers.load_test")
    load_test_module_any = cast(Any, load_test_module)
    load_test_module_any._active_test_task = None
    load_test_module_any._current_config = None
    load_test_module_any._test_history.clear()

    return app


@pytest.fixture
def isolated_client(monkeypatch: pytest.MonkeyPatch):

    """TestClient isolated from kubernetes and metrics collector side effects."""

    _ensure_kubernetes(monkeypatch)
    _StubMetricsCollector.clear_instances()
    _clear_modules()
    injected_modules = _install_stub_metrics_collector_modules()
    _mock_update_metrics(monkeypatch)
    app = _reload_app(monkeypatch)

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        for module_name in injected_modules:
            sys.modules.pop(module_name, None)



@pytest.fixture
def sample_fixture():
    """A minimal fixture for testing."""
    return {"test": "value"}


@pytest.fixture(scope="session")
def test_config():
    """Session-scoped configuration for tests."""
    return {
        "backend_url": "http://localhost:8000",
        "test_mode": True,
    }
