# routers/__init__.py
# Re-export routers with expected names for main.py
from backend.routers.load_test import router as load_test
from backend.routers.metrics import router as metrics
from backend.routers.benchmark import router as benchmark
from backend.routers.tuner import router as tuner

__all__ = ["load_test", "metrics", "benchmark", "tuner"]
