"""
Shared singleton instances for backend services.

All modules that need MetricsCollector should import from here,
not create their own instances. This ensures a single MetricsCollector
runs start_collection() and all consumers read from the same
_latest/_history.
"""
import os

from services.metrics_collector import MetricsCollector
from services.load_engine import load_engine  # re-export existing singleton
from services.storage import Storage
from services.storage_health import StorageHealthMonitor

# ── Singleton MetricsCollector ──
# startup_metrics_shim.py calls start_collection() on this instance.
# routers/metrics.py and routers/tuner.py read .latest / .history from it.
metrics_collector = MetricsCollector()

# ── Singleton Storage ──
# Async SQLite storage for benchmarks, load test history, and tuner trials.
# main.py lifespan calls storage.initialize() on startup and storage.close() on shutdown.
# Default path: /data/app.db (PVC mount). Use :memory: for testing.
storage = Storage(os.getenv("STORAGE_PATH", "/data/app.db"))

storage_health_monitor = StorageHealthMonitor(storage)
