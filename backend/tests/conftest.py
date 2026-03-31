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
    "backend.services.multi_target_collector",
    "services.multi_target_collector",
    "backend.services.auto_tuner",
    "services.auto_tuner",
    "backend.routers.load_test",
    "routers.load_test",
    "backend.routers.metrics",
    "routers.metrics",
    "backend.services.metrics_service",
    "services.metrics_service",
    "backend.routers.benchmark",
    "routers.benchmark",
    "backend.routers.tuner",
    "routers.tuner",
    "routers.vllm_config",
    "backend.routers.vllm_config",
    "routers.config",
    "backend.routers.config",
    "routers.status",
    "backend.routers.status",
    "routers",
    "backend.routers",
    "startup_metrics_shim",
    "backend.startup_metrics_shim",
    "services.shared",
    "backend.services.shared",
    "services.rate_limiter",
    "backend.services.rate_limiter",
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


class _StubMultiTargetMetricsCollector:
    """Lightweight stand-in for MultiTargetMetricsCollector."""

    instances: list["_StubMultiTargetMetricsCollector"] = []

    def __init__(self):
        self.registered: list[tuple[str, str]] = []
        self._has_label: bool | None = None
        self.start_collection_calls: list[float] = []
        self.start_requests: list[float] = []
        self.stop_called: bool = False
        self.version: str = "stub"
        self.missing_metrics: list[str] = []
        self._history: list[dict[str, Any]] = []
        self._targets: dict[str, Any] = {}
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        self.creator: str | None = module.__name__ if module else None
        _StubMultiTargetMetricsCollector.instances.append(self)

    async def start_collection(self, interval: float = 2.0):
        self.start_collection_calls.append(interval)

    def record_start_request(self, interval: float):
        self.start_requests.append(interval)

    def stop(self):
        self.stop_called = True

    async def register_target(self, namespace: str, is_name: str, cr_type: str | None = None) -> bool:
        self.registered.append((namespace, is_name))
        return True

    async def get_metrics(self, namespace: str, is_name: str) -> None:
        return None

    def get_has_monitoring_label(self, namespace: str, is_name: str) -> bool:
        return self._has_label is not None and self._has_label

    def get_history_dict(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return list(self._history)

    def _build_target_queries(self, namespace: str, is_name: str, cr_type: str | None = None) -> dict[str, str]:
        return {"tokens_per_second": f'vllm:tokens{{namespace="{namespace}"}}'}

    _token: str | None = None

    @property
    def latest(self):
        return None

    @classmethod
    def clear_instances(cls):
        cls.instances.clear()


class _DummyCustomObjectsApi:
    def get_namespaced_custom_object(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"status": {"conditions": []}}

    def patch_namespaced_custom_object(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    def delete_namespaced_custom_object(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    def create_namespaced_custom_object(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
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

    # Stub kubernetes.client.exceptions module with ApiException
    exceptions_module = sys.modules.get("kubernetes.client.exceptions")
    if exceptions_module is None:
        exceptions_module = types.ModuleType("kubernetes.client.exceptions")
        sys.modules["kubernetes.client.exceptions"] = exceptions_module

    # Define a stub ApiException class
    class _StubApiException(Exception):
        pass

    monkeypatch.setattr(exceptions_module, "ApiException", _StubApiException, raising=False)

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

    stub_multi_target_instance = _StubMultiTargetMetricsCollector()
    load_engine_module = importlib.import_module("services.load_engine")
    backend_load_engine_module = importlib.import_module("backend.services.load_engine")
    from services.runtime_config import RuntimeConfig
    from services.storage import Storage

    for module_name, load_engine_target in (
        ("services.shared", load_engine_module),
        ("backend.services.shared", backend_load_engine_module),
    ):
        stub_module = types.ModuleType(module_name)
        stub_any = cast(Any, stub_module)
        stub_any.multi_target_collector = stub_multi_target_instance
        stub_any.metrics_collector = stub_multi_target_instance
        stub_any.load_engine = load_engine_target
        stub_any.Storage = Storage
        stub_any.storage = Storage(":memory:")
        stub_any.runtime_config = RuntimeConfig(stub_multi_target_instance)
        stub_any.internal_client = None
        stub_any.external_client = None
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

    async def _stub_run(self: Any, config: Any, skip_preflight: bool = False) -> dict[str, Any]:
        self._state = load_engine_module.LoadTestState()
        self._state.status = load_engine_module.LoadTestStatus.COMPLETED
        return {}

    async def _stub_preflight(self: Any, config: Any = None) -> dict[str, Any]:
        return {"success": True}

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
    monkeypatch.setattr(
        "services.load_engine.LoadTestEngine._preflight_check",
        _stub_preflight,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.services.load_engine.LoadTestEngine._preflight_check",
        _stub_preflight,
        raising=False,
    )

    load_engine_module.load_engine._state = load_engine_module.LoadTestState()

    load_test_module = importlib.import_module("routers.load_test")
    load_test_module_any = cast(Any, load_test_module)
    load_test_module_any._active_test_task = None
    load_test_module_any._current_config = None
    # Note: _test_history was removed and replaced with persistent storage

    return app


@pytest.fixture
def isolated_client(monkeypatch: pytest.MonkeyPatch):
    """TestClient isolated from kubernetes and metrics collector side effects."""

    _ensure_kubernetes(monkeypatch)
    _StubMetricsCollector.clear_instances()
    _StubMultiTargetMetricsCollector.clear_instances()
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


@pytest.fixture(autouse=True)
def _mock_resolve_model_name(request: pytest.FixtureRequest) -> Any:
    """Prevent real HTTP calls to vLLM /v1/models in unit tests."""
    import sys
    from unittest.mock import patch as mock_patch

    if request.node.fspath.basename == "test_model_resolver.py":
        yield
        return

    async def _fast_resolve(endpoint: str = "", fallback: str = "auto") -> str:
        return fallback

    targets = [
        "services.model_resolver.resolve_model_name",
        "backend.services.model_resolver.resolve_model_name",
    ]
    for mod_name in (
        "routers.config",
        "backend.routers.config",
        "routers.benchmark",
        "backend.routers.benchmark",
    ):
        if mod_name in sys.modules:
            targets.append(f"{mod_name}.resolve_model_name")

    patches = [mock_patch(t, new=_fast_resolve) for t in targets]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


@pytest.fixture(autouse=True)
def _mock_auto_tuner_preflight() -> Any:
    """Prevent real K8s calls from AutoTuner._preflight_check in unit tests."""
    from unittest.mock import AsyncMock

    stub = AsyncMock(return_value={"success": True})
    patched: list[tuple[Any, Any]] = []
    seen_ids: set[int] = set()

    def _patch_instance(at: Any) -> None:
        if id(at) in seen_ids:
            return
        seen_ids.add(id(at))
        patched.append((at, at._preflight_check))
        at._preflight_check = stub

    for mod_name in ("routers.tuner", "backend.routers.tuner"):
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, "auto_tuner"):
            _patch_instance(mod.auto_tuner)

    def _scan_app_routes(app: Any) -> None:
        for route in getattr(app, "routes", []):
            ep = getattr(route, "endpoint", None)
            if ep and hasattr(ep, "__globals__"):
                at = ep.__globals__.get("auto_tuner")
                if at is not None:
                    _patch_instance(at)

    for _mod_name, mod in list(sys.modules.items()):
        app_obj = getattr(mod, "app", None)
        if app_obj is not None and hasattr(app_obj, "routes"):
            _scan_app_routes(app_obj)

    yield

    for instance, orig in patched:
        instance._preflight_check = orig


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
