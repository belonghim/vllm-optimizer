import time
from unittest.mock import MagicMock, patch

import pytest

from ..services import event_broadcaster as eb_module
from ..services.event_broadcaster import EventBroadcaster


@pytest.mark.asyncio
async def test_broadcast_delivers_to_subscriber() -> None:
    broadcaster = EventBroadcaster()
    q = await broadcaster.subscribe()
    payload = {"type": "trial_start", "data": {"trial_id": 0}}

    await broadcaster.broadcast(payload)

    assert not q.empty()
    assert q.get_nowait() == payload


@pytest.mark.asyncio
async def test_broadcast_delivers_to_multiple_subscribers() -> None:
    broadcaster = EventBroadcaster()
    q1 = await broadcaster.subscribe()
    q2 = await broadcaster.subscribe()
    payload = {"type": "phase", "data": {"trial_id": 1, "phase": "warmup"}}

    await broadcaster.broadcast(payload)

    assert q1.get_nowait() == payload
    assert q2.get_nowait() == payload


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue() -> None:
    broadcaster = EventBroadcaster()
    q = await broadcaster.subscribe()
    await broadcaster.unsubscribe(q)

    await broadcaster.broadcast({"type": "test"})

    assert q.empty()


@pytest.mark.asyncio
async def test_broadcast_persistence_warning_only_once() -> None:
    broadcaster = EventBroadcaster()
    q = await broadcaster.subscribe()

    await broadcaster.broadcast_persistence_warning_once()
    await broadcaster.broadcast_persistence_warning_once()

    assert q.qsize() == 1
    msg = q.get_nowait()
    assert msg["type"] == "tuning_warning"


@pytest.mark.asyncio
async def test_emit_trial_metrics_increments_prometheus_counters() -> None:
    broadcaster = EventBroadcaster()

    mock_histogram = MagicMock()
    mock_counter = MagicMock()
    mock_gauge = MagicMock()

    with (
        patch.object(eb_module, "_metrics_available", True),
        patch.object(eb_module, "tuner_trial_duration_seconds", mock_histogram),
        patch.object(eb_module, "tuner_trials_total", mock_counter),
        patch.object(eb_module, "tuner_best_score", mock_gauge),
    ):
        trial_start = time.monotonic() - 0.1
        await broadcaster.emit_trial_metrics(
            trial_start=trial_start,
            status="completed",
            best_trial=None,
            config=None,
        )

    mock_histogram.observe.assert_called_once()
    mock_counter.labels.assert_called_once_with(status="completed")
    mock_counter.labels.return_value.inc.assert_called_once()
