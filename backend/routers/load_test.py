"""
Load Test Router
Provides endpoints for starting, stopping, and monitoring load tests.
"""

import asyncio
import json
import logging
import os
import time as time_module
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from models.load_test import (
    ErrorResponse,
    LoadTestConfig,
    LoadTestResult,
    SweepConfig,
    SweepResult,
)
from pydantic import BaseModel
from services.load_engine import LoadTestStatus, load_engine
from services.model_resolver import resolve_model_name
from services.shared import storage

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory state for active test (in production, use proper state management)
_active_test_task: asyncio.Task[Any] | None = None
_current_config: LoadTestConfig | None = None
_test_lock = asyncio.Lock()

_sweep_task: asyncio.Task[Any] | None = None
_sweep_result: SweepResult | None = None
_is_sweeping: bool = False


# Simple response models for start/stop
class StartResponse(BaseModel):
    """Response when starting a load test"""

    test_id: str
    status: str
    message: str
    config: dict[str, Any]


class StopResponse(BaseModel):
    """Response when stopping a load test"""

    status: str
    test_id: str
    message: str


class StatusResponse(BaseModel):
    """Response for load test status"""

    test_id: str | None = None
    running: bool = False
    config: LoadTestConfig | None = None
    current_result: LoadTestResult | None = None
    elapsed: float = 0.0
    sweep_result: dict[str, Any] | None = None
    is_sweeping: bool = False


@router.post(
    "/start",
    response_model=StartResponse,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def start_load_test(config: LoadTestConfig) -> dict[str, Any]:
    """
    Start a new load test with the given configuration.

    - Accepts load test parameters (concurrency, RPS, prompt template, etc.)
    - Returns a test_id to track this specific test run
    - Test runs asynchronously; use /status or /stream to monitor progress
    """
    global _active_test_task, _current_config

    async with _test_lock:
        if _active_test_task is not None and not _active_test_task.done():
            raise HTTPException(
                status_code=409,
                detail=ErrorResponse(
                    error="A load test is already running.",
                    error_type="already_running",
                ).model_dump(),
            )

    test_id = str(uuid.uuid4())

    if config.model == "auto":
        try:
            config.model = await asyncio.wait_for(resolve_model_name(config.endpoint), timeout=3.0)
        except TimeoutError:
            config.model = os.getenv("VLLM_MODEL", "auto")

    preflight = await load_engine._preflight_check(config)
    if not preflight.get("success"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=preflight.get("error", "Preflight check failed"),
                error_type=preflight.get("error_type", "preflight_error"),
            ).model_dump(),
        )

    # Run test in background task
    async def run_test():
        global _active_test_task
        try:
            result = await load_engine.run(config, skip_preflight=True)
            entry = {
                "test_id": test_id,
                "config": config.model_dump(),
                "result": result,
                "timestamp": time_module.time(),
            }
            try:
                await storage.save_load_test(entry)
            except OSError as e:
                logger.warning("[LoadTest] Failed to persist history (fail-open): %s", e)
        except (
            asyncio.CancelledError,
            OSError,
            RuntimeError,
            Exception,
        ) as e:  # intentional: catch all errors during test
            logger.error("[LoadTest] Error: %s", e)
        finally:
            _active_test_task = None

    # Start the test in background
    _active_test_task = asyncio.create_task(run_test())
    _current_config = config

    return {
        "test_id": test_id,
        "status": "started",
        "message": "Load test started",
        "config": config.model_dump(),
    }


@router.post("/stop", response_model=StopResponse)
async def stop_load_test(test_id: str | None = None) -> dict[str, Any]:
    """
    Stop a running load test.

    - Requires test_id from /start response
    - Gracefully stops all worker tasks
    - Final results will be available via /status
    """
    global _active_test_task, _sweep_task, _is_sweeping

    # Stop the engine
    await load_engine.stop()

    # Cancel the active task if exists
    if _active_test_task and not _active_test_task.done():
        _active_test_task.cancel()
        _active_test_task = None

    if _sweep_task and not _sweep_task.done():
        _sweep_task.cancel()
        _sweep_task = None
        _is_sweeping = False

    return {
        "status": "stopped",
        "test_id": test_id,
        "message": "Load test stopped successfully",
    }


@router.get("/status", response_model=StatusResponse)
async def get_load_test_status(test_id: str | None = None) -> dict[str, Any]:
    """
    Get current status and intermediate results of a load test.

    - If test_id is provided, returns status for that specific test
    - If no test_id, returns status of the most recent test (if any)
    - Includes elapsed time, success/failed counts, and current latency/TPS stats
    """
    global _active_test_task, _current_config

    is_running = (
        _active_test_task is not None and not _active_test_task.done() and load_engine.status == LoadTestStatus.RUNNING
    )

    return {
        "test_id": test_id,
        "running": is_running,
        "config": _current_config,
        "current_result": None,
        "elapsed": load_engine.elapsed,
        "sweep_result": _sweep_result.model_dump() if _sweep_result else None,
        "is_sweeping": _is_sweeping,
    }


@router.post("/sweep", responses={409: {"model": ErrorResponse}})
async def start_sweep(config: SweepConfig) -> dict[str, Any]:
    global _sweep_task, _sweep_result, _is_sweeping

    async with _test_lock:
        if (_active_test_task is not None and not _active_test_task.done()) or _is_sweeping:
            raise HTTPException(
                status_code=409,
                detail=ErrorResponse(
                    error="A load test or sweep is already running.",
                    error_type="already_running",
                ).model_dump(),
            )
        _is_sweeping = True
        _sweep_result = None

    if config.model == "auto":
        try:
            config.model = await asyncio.wait_for(resolve_model_name(config.endpoint), timeout=3.0)
        except TimeoutError:
            config.model = os.getenv("VLLM_MODEL", "auto")

    async def run_sweep_task():
        global _sweep_task, _sweep_result, _is_sweeping
        try:
            result = await load_engine.run_sweep(config)
            _sweep_result = result
            await load_engine._broadcast({"type": "sweep_completed", "data": result.model_dump()})
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("[Sweep] Error: %s", e)
            await load_engine._broadcast({"type": "sweep_completed", "data": None})
        finally:
            _is_sweeping = False
            _sweep_task = None

    _sweep_task = asyncio.create_task(run_sweep_task())

    return {"status": "running", "config": config.model_dump()}


@router.get("/stream")
async def stream_load_test_results(test_id: str | None = None) -> StreamingResponse:
    """
    Server-Sent Events (SSE) endpoint for real-time load test results.

    - Streams incremental results as the test runs
    - Each event contains a RequestResult or partial LoadTestResult
    - Connection stays open until test completes or client disconnects
    - Sends keepalive comments every 15s to prevent proxy/browser timeouts
    - Use EventSource in frontend to consume this stream
    """
    queue = await load_engine.subscribe()

    async def event_generator():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(data)}\n\n"
                    event_type = data.get("type")
                    # During sweep: only break on sweep_completed or stopped
                    # During regular test: break on completed or stopped
                    if _is_sweeping:
                        if event_type in ("sweep_completed", "stopped"):
                            break
                    else:
                        if event_type in ("completed", "stopped"):
                            break
                except TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await load_engine.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/history",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_load_test_history(limit: int = 10) -> list[dict[str, Any]]:
    """
    Get list of recent load test runs and their final results.

    - Returns summary of completed tests (test_id, config, final result)
    - Sorted by most recent first
    - Limit parameter controls number of results returned
    """
    try:
        return await storage.get_load_test_history(limit=limit)
    except OSError as e:
        logger.warning("[LoadTest] Failed to retrieve history (fail-open): %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="스토리지 조회 실패",
                error_type="storage",
            ).model_dump(),
        ) from e
