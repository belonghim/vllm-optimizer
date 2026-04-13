# routers/__init__.py
# Re-export routers with expected names for main.py
from routers.alerts import router as alerts
from routers.benchmark import router as benchmark
from routers.config import router as config
from routers.load_test import router as load_test
from routers.metrics import router as metrics
from routers.sla import router as sla
from routers.status import router as status
from routers.tuner import router as tuner
from routers.vllm_config import router as vllm_config
from routers.targets import router as targets

__all__ = ["load_test", "metrics", "benchmark", "tuner", "vllm_config", "config", "status", "sla", "alerts", "targets"]
