"""
Async unit tests for LoadTestEngine.run() result collection behavior.

TDD RED phase — these tests FAIL before the bug fix is applied.

Bugs being tested:
- Bug 1: asyncio.wait([t for t in tasks if not t.done()], timeout=0) silently
  drops tasks that completed during asyncio.sleep(interval) between loop iterations.
- Bug 3: Final asyncio.gather loop never updates completed_requests/failed_requests.
- Bug 4: asyncio.wait([]) ValueError when task list is empty.
"""
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from services.load_engine import LoadTestEngine
from models.load_test import LoadTestConfig


def _make_mock_httpx_client():
    """Mock httpx.AsyncClient with asyncio.sleep(0) to force event loop yield.

    The sleep(0) is critical: it causes single_request() to yield control back
    to the event loop ONCE, so the task completes during the outer
    asyncio.sleep(interval). At that point, the task is .done()=True and gets
    filtered out by the buggy `not t.done()` check,
    so its result is never collected. Most of 20 results are lost.
    """
    async def _post(url, json=None, **kwargs):
        await asyncio.sleep(0)  # Force event loop yield — DO NOT REMOVE
        resp = MagicMock()
        resp.json.return_value = {"usage": {"completion_tokens": 10}}
        return resp

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = _post
    return mock_client


async def test_run_collects_all_results_when_tasks_complete_during_sleep():
    """All 20 results must be collected even when tasks finish during sleep intervals.

    With rps=5, interval=0.2s. The mock task yields once (sleep(0)), then
    completes during the outer asyncio.sleep(0.2s). At that point, the task
    is .done()=True and gets filtered out by the buggy `not t.done()` check,
    so its result is never collected. Most of 20 results are lost.

    FAILS BEFORE FIX: len(results) << 20
    PASSES AFTER FIX: len(results) == 20
    """
    engine = LoadTestEngine()
    config = LoadTestConfig(
        total_requests=20,
        rps=5,
        concurrency=20,
        stream=False,
        endpoint="http://test",
        model="test-model",
    )
    with patch("httpx.AsyncClient", return_value=_make_mock_httpx_client()):
        final_stats = await engine.run(config)

    assert len(engine._state.results) == 20, (
        f"Expected 20 results, got {len(engine._state.results)}"
    )
    assert engine._state.completed_requests == 20, (
        f"Expected completed_requests=20, got {engine._state.completed_requests}"
    )
    req_ids = {r.req_id for r in engine._state.results}
    assert len(req_ids) == 20, (
        f"Expected 20 unique req_ids, got {len(req_ids)} — duplicates present"
    )
    assert final_stats["total"] == 20, (
        f"Expected final_stats['total']=20, got {final_stats.get('total')}"
    )


async def test_run_counter_matches_result_count():
    """completed_requests + failed_requests must equal total_requests.

    With rps=0 (no sleep), tasks complete and go through the final asyncio.gather
    path. Bug 3: the gather loop appends results but never increments the counters.
    After run(), counters are less than total_requests even though results are collected.
    
    FAILS BEFORE FIX: completed+failed=10
    PASSES AFTER FIX: sum == 10
    """
    engine = LoadTestEngine()
    config = LoadTestConfig(
        total_requests=10,
        rps=0,
        concurrency=10,
        stream=False,
        endpoint="http://test",
        model="test-model",
    )
    with patch("httpx.AsyncClient", return_value=_make_mock_httpx_client()):
        await engine.run(config)

    total_counted = engine._state.completed_requests + engine._state.failed_requests
    assert total_counted == 10, (
        f"Expected completed+failed=10, got {engine._state.completed_requests}"
        f"+{engine._state.failed_requests}={total_counted}"
    )


async def test_run_no_valueerror_when_all_tasks_done_instantly():
    """run() must complete without ValueError even when all tasks finish instantly.

    Bug 4: asyncio.wait([]) raises ValueError when passed an empty task list.
    With an instant mock (no sleep(0)), all tasks can complete during a single
    event loop step, potentially leaving an empty list for asyncio.wait.
    """
    engine = LoadTestEngine()
    config = LoadTestConfig(
        total_requests=5,
        rps=0,
        concurrency=5,
        stream=False,
        endpoint="http://test",
        model="test-model",
    )

    # Instant mock — no sleep(0), tasks complete in one event loop step
    async def _instant_post(url, json=None, **kwargs):
        resp = MagicMock()
        resp.json.return_value = {"usage": {"completion_tokens": 10}}
        return resp

    instant_mock = MagicMock()
    instant_mock.__aenter__ = AsyncMock(return_value=instant_mock)
    instant_mock.__aexit__ = AsyncMock(return_value=False)
    instant_mock.post = _instant_post

    with patch("httpx.AsyncClient", return_value=instant_mock):
        final_stats = await engine.run(config)

    assert isinstance(final_stats, dict), "run() must return a dict"
    assert len(final_stats) > 0, "final_stats must not be empty"


async def test_run_failed_requests_counted_correctly():
    """failed_requests counter must reflect requests that raised exceptions.

    Even-indexed requests (0,2,4,6,8) raise Exception — 5 failures total.
    The final gather path (Bug 3) never updates failed_requests, so the counter
    stays at 0 despite 5 errors being processed.

    FAILS BEFORE FIX: failed_requests < 5 OR len(results) < 10
    PASSES AFTER FIX: failed_requests==5 AND len(results)==10
    """
    engine = LoadTestEngine()
    config = LoadTestConfig(
        total_requests=10,
        rps=0,
        concurrency=10,
        stream=False,
        endpoint="http://test",
        model="test-model",
    )

    call_n = {"n": 0}

    async def _alternating_post(url, json=None, **kwargs):
        await asyncio.sleep(0)
        idx = call_n["n"]
        call_n["n"] += 1
        if idx % 2 == 0:
            raise Exception("mock error")
        resp = MagicMock()
        resp.json.return_value = {"usage": {"completion_tokens": 10}}
        return resp

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = _alternating_post

    with patch("httpx.AsyncClient", return_value=mock_client):
        await engine.run(config)

    assert engine._state.failed_requests == 5, (
        f"Expected 5 failed requests, got {engine._state.failed_requests}"
    )
    assert len(engine._state.results) == 10, (
        f"Expected 10 total results, got {len(engine._state.results)}"
    )


async def test_run_no_duplicate_results():
    """Each request must appear exactly once in results — no duplicates.

    If a task's result is collected in BOTH the loop body AND the final gather,
    its req_id appears twice. With rps=10 and the sleep(0) mock, some tasks
    complete during sleep and risk double-collection.

    FAILS BEFORE FIX: duplicate req_ids present (if double-collection occurs)
    or too few results (if under-collection dominates)
    PASSES AFTER FIX: exactly 15 unique req_ids
    """
    engine = LoadTestEngine()
    config = LoadTestConfig(
        total_requests=15,
        rps=10,
        concurrency=15,
        stream=False,
        endpoint="http://test",
        model="test-model",
    )
    with patch("httpx.AsyncClient", return_value=_make_mock_httpx_client()):
        await engine.run(config)

    req_ids = [r.req_id for r in engine._state.results]
    assert len(req_ids) == len(set(req_ids)), (
        f"Duplicate req_ids found: {len(req_ids)} total vs {len(set(req_ids))} unique"
    )
