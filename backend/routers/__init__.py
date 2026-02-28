# routers/__init__.py
# Re-export routers with expected names for main.py
from .load_test import router as load_test
from .metrics import router as metrics
from .benchmark import router as benchmark
from .tuner import router as tuner

__all__ = ["load_test", "metrics", "benchmark", "tuner"]
