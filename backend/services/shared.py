import os

from services.multi_target_collector import MultiTargetMetricsCollector
from services.load_engine import load_engine  # re-export existing singleton
from services.storage import Storage
from services.storage_health import StorageHealthMonitor
from services.runtime_config import RuntimeConfig

multi_target_collector = MultiTargetMetricsCollector()

runtime_config = RuntimeConfig(multi_target_collector)

storage = Storage(os.getenv("STORAGE_PATH", "/data/app.db"))

storage_health_monitor = StorageHealthMonitor(storage)

__all__ = [
    "runtime_config",
    "multi_target_collector",
    "load_engine",
    "storage",
    "storage_health_monitor",
]
