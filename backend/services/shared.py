import os

import httpx

from services.load_engine import load_engine  # re-export existing singleton
from services.multi_target_collector import MultiTargetMetricsCollector
from services.runtime_config_instance import runtime_config
from services.storage import Storage
from services.storage_health import StorageHealthMonitor

multi_target_collector = MultiTargetMetricsCollector()

runtime_config._multi_target_collector = multi_target_collector

storage = Storage(os.getenv("STORAGE_PATH", "/data/app.db"))

storage_health_monitor = StorageHealthMonitor(storage)

# Lazy-initialized httpx clients (initialized in main.py lifespan or on-demand)
_internal_client: httpx.AsyncClient | None = None
_external_client: httpx.AsyncClient | None = None

# Public module-level access (for backward compatibility with tests/main.py)
internal_client: httpx.AsyncClient | None = None
external_client: httpx.AsyncClient | None = None


def get_internal_client() -> httpx.AsyncClient:
    """Get or lazily initialize internal httpx client (TLS verification disabled).

    Priority: public module variable (set by main.py) > private lazy init.
    This maintains backward compatibility with main.py's lifespan initialization.
    """
    # Check if main.py already set the public variable in startup
    if internal_client is not None:
        return internal_client

    # Otherwise, lazy-initialize the private one
    global _internal_client
    if _internal_client is None:
        ca_bundle = os.environ.get("CA_BUNDLE", "")
        verify = ca_bundle if ca_bundle else False
        _internal_client = httpx.AsyncClient(verify=verify, timeout=httpx.Timeout(30.0, connect=10.0))
    return _internal_client


def get_external_client() -> httpx.AsyncClient:
    """Get or lazily initialize external httpx client (standard TLS verification).

    Priority: public module variable (set by main.py) > private lazy init.
    This maintains backward compatibility with main.py's lifespan initialization.
    """
    # Check if main.py already set the public variable in startup
    if external_client is not None:
        return external_client

    # Otherwise, lazy-initialize the private one
    global _external_client
    if _external_client is None:
        ca_bundle = os.environ.get("CA_BUNDLE", "")
        verify = ca_bundle if ca_bundle else True
        _external_client = httpx.AsyncClient(verify=verify, timeout=httpx.Timeout(30.0, connect=10.0))
    return _external_client


__all__ = [
    "runtime_config",
    "multi_target_collector",
    "load_engine",
    "storage",
    "storage_health_monitor",
    "internal_client",
    "external_client",
    "get_internal_client",
    "get_external_client",
]
