"""
SSE event_generator 동작 단위 테스트
- heartbeat keepalive (idle 시 ": keepalive" comment 전송)
- completed 이벤트 후 generator 자동 종료 및 subscriber 정리
"""

import asyncio
import json

import pytest


async def test_event_generator_sends_keepalive_on_idle():
    """큐에 데이터 없을 시 timeout 후 keepalive comment 전송"""
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()
    q = await engine.subscribe()
    collected = []

    async def generator():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=0.1)  # 테스트용 짧은 타임아웃
                    collected.append(f"data: {json.dumps(data)}\n\n")
                    if data.get("type") in ("completed", "stopped"):
                        break
                except TimeoutError:
                    collected.append(": keepalive\n\n")
                    break  # 첫 keepalive 후 종료 (테스트용)
        finally:
            await engine.unsubscribe(q)

    await asyncio.wait_for(generator(), timeout=2.0)

    assert len(collected) == 1, f"Expected 1 keepalive, got {len(collected)}: {collected}"
    assert collected[0] == ": keepalive\n\n", f"Expected keepalive comment, got: {collected[0]!r}"
    assert len(engine._subscribers) == 0, "Subscriber not cleaned up after keepalive"


async def test_event_generator_breaks_after_completed_event():
    """completed 이벤트 수신 후 generator 루프 종료 및 subscriber 정리"""
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()
    q = await engine.subscribe()
    collected = []

    async def generator():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=1.0)
                    collected.append(f"data: {json.dumps(data)}\n\n")
                    if data.get("type") in ("completed", "stopped"):
                        break
                except TimeoutError:
                    collected.append(": keepalive\n\n")
        finally:
            await engine.unsubscribe(q)

    await engine._broadcast({"type": "completed", "data": {"total": 10}})

    await asyncio.wait_for(generator(), timeout=2.0)

    assert len(collected) == 1
    assert '"type": "completed"' in collected[0]
    assert len(engine._subscribers) == 0, f"Subscriber leak! {len(engine._subscribers)} remain"


async def test_event_generator_sends_data_before_keepalive():
    """데이터 이벤트는 keepalive 없이 즉시 전달"""
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()
    q = await engine.subscribe()
    collected = []

    async def generator():
        try:
            for _ in range(2):
                try:
                    data = await asyncio.wait_for(q.get(), timeout=1.0)
                    collected.append(f"data: {json.dumps(data)}\n\n")
                    if data.get("type") in ("completed", "stopped"):
                        break
                except TimeoutError:
                    collected.append(": keepalive\n\n")
        finally:
            await engine.unsubscribe(q)

    await engine._broadcast({"type": "progress", "data": {"total": 1}})
    await engine._broadcast({"type": "completed", "data": {"total": 1}})

    await asyncio.wait_for(generator(), timeout=2.0)

    assert len(collected) == 2
    assert all(c.startswith("data: ") for c in collected)
    assert not any(c.startswith(": keepalive") for c in collected)


async def test_broadcast_terminal_records_last_event_and_clear_resets():
    """터미널 이벤트는 마지막 이벤트로 기록되고 clear로 제거된다."""
    from services.load_engine import LoadTestEngine

    engine = LoadTestEngine()
    assert engine.last_terminal_event is None

    await engine.broadcast_terminal({"type": "error", "data": {"error": "boom"}})
    assert engine.last_terminal_event is not None
    assert engine.last_terminal_event["type"] == "error"

    engine.clear_terminal_event()
    assert engine.last_terminal_event is None


async def test_late_subscriber_receives_terminal_replay():
    """완료 후 늦게 구독한 클라이언트는 재생된 터미널 이벤트를 받고 스트림이 종료된다."""
    from routers.load_test import load_engine, stream_load_test_results

    load_engine.clear_terminal_event()
    await load_engine.broadcast_terminal({"type": "completed", "data": {"total": 3}})

    response = await stream_load_test_results(test_id=None)
    first_chunk = await response.body_iterator.__anext__()
    assert '"type": "completed"' in first_chunk
    assert '"total": 3' in first_chunk
    with pytest.raises(StopAsyncIteration):
        await response.body_iterator.__anext__()

    load_engine.clear_terminal_event()


async def test_stop_broadcasts_stopped_terminal_when_running():
    """실행 중 stop()은 stopped 터미널 이벤트를 브로드캐스트하고 기록한다."""
    from services.load_engine import LoadTestEngine, LoadTestStatus

    engine = LoadTestEngine()
    engine._state.status = LoadTestStatus.RUNNING
    q = await engine.subscribe()

    await engine.stop()

    assert q.get_nowait()["type"] == "stopped"
    assert engine.last_terminal_event is not None
    assert engine.last_terminal_event["type"] == "stopped"
