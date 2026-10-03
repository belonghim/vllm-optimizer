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
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from models.load_test import LoadTestConfig, RequestResult
from services.load_engine import LoadTestEngine


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
        resp.status_code = 200
        resp.json.return_value = {"usage": {"completion_tokens": 10}}
        return resp

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = _post
    _preflight_resp = MagicMock()
    _preflight_resp.status_code = 400
    mock_client.get = AsyncMock(return_value=_preflight_resp)
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
    with patch("services.shared.external_client", _make_mock_httpx_client()):
        final_stats = await engine.run(config, skip_preflight=True)

    assert len(engine._state.results) == 20, f"Expected 20 results, got {len(engine._state.results)}"
    assert engine._state.completed_requests == 20, (
        f"Expected completed_requests=20, got {engine._state.completed_requests}"
    )
    req_ids = {r.req_id for r in engine._state.results}
    assert len(req_ids) == 20, f"Expected 20 unique req_ids, got {len(req_ids)} — duplicates present"
    assert final_stats["total"] == 20, f"Expected final_stats['total']=20, got {final_stats.get('total')}"


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
    with patch("services.shared.external_client", _make_mock_httpx_client()):
        await engine.run(config, skip_preflight=True)

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
        resp.status_code = 200
        resp.json.return_value = {"usage": {"completion_tokens": 10}}
        return resp

    instant_mock = MagicMock()
    instant_mock.__aenter__ = AsyncMock(return_value=instant_mock)
    instant_mock.__aexit__ = AsyncMock(return_value=False)
    instant_mock.post = _instant_post
    _instant_preflight_resp = MagicMock()
    _instant_preflight_resp.status_code = 400
    instant_mock.get = AsyncMock(return_value=_instant_preflight_resp)

    with patch("services.shared.external_client", instant_mock):
        final_stats = await engine.run(config, skip_preflight=True)

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
            raise httpx.ConnectError("mock error")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"usage": {"completion_tokens": 10}}
        return resp

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = _alternating_post
    _alt_preflight_resp = MagicMock()
    _alt_preflight_resp.status_code = 400
    mock_client.get = AsyncMock(return_value=_alt_preflight_resp)

    with patch("services.shared.external_client", mock_client):
        await engine.run(config, skip_preflight=True)

    assert engine._state.failed_requests == 5, f"Expected 5 failed requests, got {engine._state.failed_requests}"
    assert len(engine._state.results) == 10, f"Expected 10 total results, got {len(engine._state.results)}"


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
    with patch("services.shared.external_client", _make_mock_httpx_client()):
        await engine.run(config, skip_preflight=True)

    req_ids = [r.req_id for r in engine._state.results]
    assert len(req_ids) == len(set(req_ids)), (
        f"Duplicate req_ids found: {len(req_ids)} total vs {len(set(req_ids))} unique"
    )


async def test_compute_stats_rps_actual_counts_only_successful_requests():
    """rps_actual must reflect achieved goodput, not requests that errored out.

    Counting failures would report high throughput for a server that rejects
    every request, and would disagree with the guidellm parser path
    (guidellm_parser.py computes successful/elapsed).
    """
    engine = LoadTestEngine()
    engine._state.start_time = 998.0
    engine._state.results = [
        RequestResult(req_id=1, success=True, latency=0.1),
        RequestResult(req_id=2, success=True, latency=0.1),
        RequestResult(req_id=3, success=False, latency=0.05, error="HTTP 500"),
        RequestResult(req_id=4, success=False, latency=0.05, error="HTTP 500"),
    ]

    with patch("services.load_engine.time.time", return_value=1000.0):
        stats = engine._compute_stats()

    assert stats["total"] == 4
    assert stats["success"] == 2
    assert stats["rps_actual"] == 1.0


async def test_api_key_sent_as_bearer_and_never_serialized():
    captured: dict = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"usage": {"completion_tokens": 3}}

    class _Client:
        async def post(self, url, json=None, timeout=None, headers=None):
            captured["headers"] = headers
            return _Resp()

    config = LoadTestConfig(endpoint="https://maas/ns/m", model="m", stream=False, api_key="sk-secret")
    engine = LoadTestEngine()
    payload = engine._build_request_payload(config, "hi")
    result = await engine._dispatch_completions(config, payload, _Client(), 0.0, 1)

    assert result.success is True
    assert captured["headers"] == {"Authorization": "Bearer sk-secret"}
    assert "api_key" not in config.model_dump()
    assert "sk-secret" not in repr(config)


def test_find_knee_rps_maximizes_throughput_per_latency():
    from models.load_test import SweepStepResult
    from services.load_engine import find_knee_rps

    def step(rps, tps, lat, failed=0):
        return SweepStepResult(
            step=int(rps),
            rps=rps,
            stats={"total": 20, "failed": failed, "tps": {"total": tps}, "latency": {"mean": lat}},
        )

    steps = [
        step(1, 100, 1.0),  # power 100
        step(5, 450, 1.5),  # power 300  <- knee
        step(10, 600, 3.0),  # power 200 (throughput still rising, latency doubling)
        step(15, 2000, 1.0, failed=10),  # 50% errors: excluded
    ]
    assert find_knee_rps(steps, max_error_rate=0.1) == 5
    assert find_knee_rps([], max_error_rate=0.1) is None
