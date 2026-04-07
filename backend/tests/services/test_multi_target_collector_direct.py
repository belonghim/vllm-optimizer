from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from services.multi_target_collector import MultiTargetMetricsCollector, TargetCache


def _make_target() -> TargetCache:
    return TargetCache(
        key="ns/name/inferenceservice",
        namespace="ns",
        is_name="name",
        cr_type="inferenceservice",
        is_default=True,
    )


def _make_collector_with_running_pod(ip: str = "10.0.0.10") -> MultiTargetMetricsCollector:
    collector = MultiTargetMetricsCollector()
    collector._k8s_available = True
    collector._k8s_core = MagicMock()

    pod = MagicMock()
    pod.status = SimpleNamespace(
        phase="Running",
        pod_ip=ip,
        container_statuses=[SimpleNamespace(ready=True)],
    )
    pod.metadata = SimpleNamespace(name="pod-0")
    pod.spec = SimpleNamespace(node_name=None)

    collector._k8s_core.list_namespaced_pod.return_value = SimpleNamespace(items=[pod])
    return collector


@pytest.mark.asyncio
async def test_direct_swapped_requests() -> None:
    collector = _make_collector_with_running_pod()
    target = _make_target()

    with (
        patch.object(collector, "_scrape_pod_metrics", new=AsyncMock(return_value={"swapped_requests": 3.0})),
        patch("services.multi_target_collector.update_metrics", lambda *args, **kwargs: None),
    ):
        await collector._collect_target_direct(target)

    assert target.latest is not None
    assert target.latest.swapped_requests == 3


@pytest.mark.asyncio
async def test_direct_tpot_mean_and_p99() -> None:
    collector = _make_collector_with_running_pod()
    target = _make_target()

    with (
        patch.object(
            collector,
            "_scrape_pod_metrics",
            new=AsyncMock(
                return_value={
                    "tpot_sum": 1.0,
                    "tpot_count": 10.0,
                    "tpot_buckets": [(0.01, 1.0), (0.05, 6.0), (0.1, 9.0), (float("inf"), 10.0)],
                }
            ),
        ),
        patch("services.multi_target_collector.update_metrics", lambda *args, **kwargs: None),
    ):
        await collector._collect_target_direct(target)

    assert target.latest is not None
    assert target.latest.mean_tpot_ms == pytest.approx(100.0)
    assert target.latest.p99_tpot_ms > 0


@pytest.mark.asyncio
async def test_direct_queue_time_mean_and_p99() -> None:
    collector = _make_collector_with_running_pod()
    target = _make_target()

    with (
        patch.object(
            collector,
            "_scrape_pod_metrics",
            new=AsyncMock(
                return_value={
                    "queue_time_sum": 1.0,
                    "queue_time_count": 10.0,
                    "queue_time_buckets": [(0.01, 2.0), (0.05, 8.0), (0.1, 10.0), (float("inf"), 10.0)],
                }
            ),
        ),
        patch("services.multi_target_collector.update_metrics", lambda *args, **kwargs: None),
    ):
        await collector._collect_target_direct(target)

    assert target.latest is not None
    assert target.latest.mean_queue_time_ms == pytest.approx(100.0)
    assert target.latest.p99_queue_time_ms > 0


@pytest.mark.asyncio
async def test_direct_cr_exists_set() -> None:
    collector = _make_collector_with_running_pod()
    target = _make_target()

    with (
        patch.object(collector, "_scrape_pod_metrics", new=AsyncMock(return_value={})),
        patch.object(
            collector,
            "_check_cr_exists",
            new=AsyncMock(side_effect=lambda t: setattr(t, "cr_exists", True)),
        ),
        patch("services.multi_target_collector.update_metrics", lambda *args, **kwargs: None),
    ):
        await collector._collect_target_direct(target)

    assert target.cr_exists is True
