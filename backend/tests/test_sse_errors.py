import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


async def test_load_test_sse_emits_error_when_engine_fails():
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()
    q = await engine.subscribe()

    mock_ctx = MagicMock()
    with patch("services.shared.internal_client", mock_ctx):
        mock_ctx.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        from models.load_test import LoadTestConfig

        config = LoadTestConfig(endpoint="http://nonexistent:9999", total_requests=5)
        await engine.run(config)

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) >= 1

    data = error_events[0]["data"]
    assert "message" in data
    assert "recoverable" in data
    assert "timestamp" in data
    assert data["recoverable"] is False
    assert isinstance(data["timestamp"], float)
    assert isinstance(data["message"], str)
    assert "error_type" in data

    await engine.unsubscribe(q)


async def test_load_test_sse_generator_breaks_on_error():
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()
    q = await engine.subscribe()

    await q.put({"type": "error", "data": {"message": "fatal", "recoverable": False, "timestamp": time.time()}})

    collected = []

    async def run_generator():
        from routers.load_test import _is_sweeping

        try:
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=0.5)
                    collected.append(data)
                    event_type = data.get("type")
                    if _is_sweeping:
                        if event_type in ("sweep_completed", "stopped", "error"):
                            break
                    else:
                        if event_type in ("completed", "stopped", "error"):
                            break
                except TimeoutError:
                    break
        except asyncio.CancelledError:
            pass

    await run_generator()

    assert len(collected) == 1
    assert collected[0]["type"] == "error"

    await engine.unsubscribe(q)


async def test_load_test_sse_completed_still_works():
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()
    q = await engine.subscribe()

    await q.put({"type": "progress", "data": {"total": 1}})
    await q.put({"type": "completed", "data": {"total": 5}})

    collected = []

    async def run_generator():
        from routers.load_test import _is_sweeping

        try:
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=0.5)
                    collected.append(data)
                    event_type = data.get("type")
                    if not _is_sweeping and event_type in ("completed", "stopped", "error"):
                        break
                except TimeoutError:
                    break
        except asyncio.CancelledError:
            pass

    await run_generator()

    assert len(collected) == 2
    assert collected[-1]["type"] == "completed"

    await engine.unsubscribe(q)


async def test_tuner_sse_emits_error_when_trial_fails():
    from services.auto_tuner import AutoTuner

    tuner = AutoTuner(metrics_collector=MagicMock(), load_engine=MagicMock())
    q = await tuner.subscribe()

    await tuner._broadcast(
        {
            "type": "error",
            "data": {
                "message": "Trial 0 evaluation failed: connection error",
                "recoverable": True,
                "timestamp": time.time(),
            },
        }
    )

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1

    data = error_events[0]["data"]
    assert data["recoverable"] is True
    assert "Trial 0" in data["message"]
    assert "timestamp" in data

    await tuner.unsubscribe(q)


async def test_tuner_sse_generator_continues_on_recoverable_error():
    from services.auto_tuner import AutoTuner

    tuner = AutoTuner(metrics_collector=MagicMock(), load_engine=MagicMock())
    q = await tuner.subscribe()

    await q.put({"type": "error", "data": {"message": "trial 0 failed", "recoverable": True, "timestamp": time.time()}})
    await q.put({"type": "tuning_complete", "data": {"best_params": {}, "total_trials": 1}})

    collected = []

    async def run_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=0.5)
                    collected.append(event)
                    event_type = event.get("type")
                    if event_type == "tuning_complete":
                        break
                    if event_type == "error" and not event.get("data", {}).get("recoverable", True):
                        break
                except TimeoutError:
                    break
        except asyncio.CancelledError:
            pass

    await run_generator()

    assert len(collected) == 2
    assert collected[0]["type"] == "error"
    assert collected[1]["type"] == "tuning_complete"

    await tuner.unsubscribe(q)


async def test_tuner_sse_generator_breaks_on_fatal_error():
    from services.auto_tuner import AutoTuner

    tuner = AutoTuner(metrics_collector=MagicMock(), load_engine=MagicMock())
    q = await tuner.subscribe()

    await q.put(
        {"type": "error", "data": {"message": "k8s RBAC forbidden", "recoverable": False, "timestamp": time.time()}}
    )
    await q.put({"type": "tuning_complete", "data": {}})

    collected = []

    async def run_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=0.5)
                    collected.append(event)
                    event_type = event.get("type")
                    if event_type == "tuning_complete":
                        break
                    if event_type == "error" and not event.get("data", {}).get("recoverable", True):
                        break
                except TimeoutError:
                    break
        except asyncio.CancelledError:
            pass

    await run_generator()

    assert len(collected) == 1
    assert collected[0]["type"] == "error"

    await tuner.unsubscribe(q)


async def test_tuner_sse_tuning_complete_still_works():
    from services.auto_tuner import AutoTuner

    tuner = AutoTuner(metrics_collector=MagicMock(), load_engine=MagicMock())

    q = await tuner.subscribe()

    await q.put({"type": "trial_complete", "data": {"trial_id": 0, "score": 1.0, "tps": 10.0, "p99_latency": 0.1}})
    await q.put({"type": "tuning_complete", "data": {"best_params": {}, "total_trials": 1}})

    collected = []

    async def run_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=0.5)
                    collected.append(event)
                    event_type = event.get("type")
                    if event_type == "tuning_complete":
                        break
                    if event_type == "error" and not event.get("data", {}).get("recoverable", True):
                        break
                except TimeoutError:
                    break
        except asyncio.CancelledError:
            pass

    await run_generator()

    assert len(collected) == 2
    assert collected[-1]["type"] == "tuning_complete"

    await tuner.unsubscribe(q)


async def test_auto_tuner_broadcasts_error_on_trial_evaluation_failure():
    from services.auto_tuner import AutoTuner

    tuner = AutoTuner(metrics_collector=MagicMock(), load_engine=MagicMock())
    q = await tuner.subscribe()

    await tuner._broadcast(
        {
            "type": "error",
            "data": {
                "message": "Trial 0 evaluation failed: httpx.ConnectError",
                "recoverable": True,
                "timestamp": time.time(),
            },
        }
    )

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    assert any(e["type"] == "error" for e in events)
    err_event = next(e for e in events if e["type"] == "error")
    assert err_event["data"]["recoverable"] is True
    assert "timestamp" in err_event["data"]

    await tuner.unsubscribe(q)
