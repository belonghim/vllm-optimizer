"""
SSE event_generator 동작 단위 테스트
- heartbeat keepalive (idle 시 ": keepalive" comment 전송)
- completed 이벤트 후 generator 자동 종료 및 subscriber 정리
"""

import asyncio
import json


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
