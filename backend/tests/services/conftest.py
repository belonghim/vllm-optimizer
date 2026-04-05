import pytest

from backend.services.multi_target_collector import MultiTargetMetricsCollector


@pytest.fixture
def collector() -> MultiTargetMetricsCollector:
    c = MultiTargetMetricsCollector()
    c._k8s_available = False
    c._k8s_core = None
    return c
