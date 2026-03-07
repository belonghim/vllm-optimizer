"""
Shared singleton instances for backend services.

All modules that need MetricsCollector should import from here,
not create their own instances. This ensures a single MetricsCollector
runs start_collection() and all consumers read from the same
_latest/_history.
"""
from services.metrics_collector import MetricsCollector
from services.load_engine import load_engine  # re-export existing singleton

# ── Singleton MetricsCollector ──
# startup_metrics_shim.py calls start_collection() on this instance.
# routers/metrics.py and routers/tuner.py read .latest / .history from it.
metrics_collector = MetricsCollector()
