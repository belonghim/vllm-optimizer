import os

from services.load_engine import load_engine  # re-export existing singleton
from services.multi_target_collector import MultiTargetMetricsCollector
from services.runtime_config_instance import runtime_config
from services.storage import Storage
from services.storage_health import StorageHealthMonitor

multi_target_collector = MultiTargetMetricsCollector()

runtime_config._multi_target_collector = multi_target_collector

storage = Storage(os.getenv("STORAGE_PATH", "/data/app.db"))

storage_health_monitor = StorageHealthMonitor(storage)

__all__ = [
    "runtime_config",
    "multi_target_collector",
    "load_engine",
    "storage",
    "storage_health_monitor",
]
