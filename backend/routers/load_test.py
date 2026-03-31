"""
Load Test Router
Provides endpoints for starting, stopping, and monitoring load tests.
"""

import asyncio
import json
import logging
import os
import sqlite3
import time as time_module
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
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
from services.rate_limiter import limiter

router = APIRouter()
logger = logging.getLogger(__name__)


def get_storage() -> Any:
    """Return the shared storage instance."""
    from services import shared

    return shared.storage


class LoadTestState:
    def __init__(self) -> None:
        self._active_test_task: asyncio.Task[None] | None = None
        self._current_config: LoadTestConfig | None = None
        self._sweep_task: asyncio.Task[None] | None = None
        self._sweep_result: SweepResult | None = None
        self._is_sweeping: bool = False
        self._test_lock: asyncio.Lock = asyncio.Lock()

    async def has_running_test(self) -> bool:
        async with self._test_lock:
            return self._active_test_task is not None and not self._active_test_task.done()

    async def set_active_test(self, task: asyncio.Task[None], config: LoadTestConfig) -> None:
        async with self._test_lock:
            self._active_test_task = task
            self._current_config = config

    async def clear_active_test(self) -> None:
        async with self._test_lock:
            self._active_test_task = None

    async def cancel_active_test(self) -> None:
        async with self._test_lock:
            if self._active_test_task and not self._active_test_task.done():
                _ = self._active_test_task.cancel()
                self._active_test_task = None

    async def get_status_snapshot(
        self,
    ) -> tuple[asyncio.Task[None] | None, LoadTestConfig | None, SweepResult | None, bool]:
        async with self._test_lock:
            return self._active_test_task, self._current_config, self._sweep_result, self._is_sweeping

    async def can_start_sweep(self) -> bool:
        async with self._test_lock:
            return (self._active_test_task is None or self._active_test_task.done()) and not self._is_sweeping

    async def mark_sweep_started(self) -> None:
        async with self._test_lock:
            self._is_sweeping = True
            self._sweep_result = None

    async def set_sweep_task(self, task: asyncio.Task[None]) -> None:
        async with self._test_lock:
            self._sweep_task = task

    async def set_sweep_result(self, result: SweepResult) -> None:
        async with self._test_lock:
            self._sweep_result = result

    async def finish_sweep(self) -> None:
        async with self._test_lock:
            self._is_sweeping = False
            self._sweep_task = None

    async def cancel_sweep_if_running(self) -> None:
        async with self._test_lock:
            if self._sweep_task and not self._sweep_task.done():
                _ = self._sweep_task.cancel()
                self._sweep_task = None
                self._is_sweeping = False

    async def is_sweeping(self) -> bool:
        async with self._test_lock:
            return self._is_sweeping


_state = LoadTestState()


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


async def _run_test_background(test_id: str, config: LoadTestConfig, storage_instance: Any) -> None:
    try:
        result = await load_engine.run(config, skip_preflight=True)
        entry = {
            "test_id": test_id,
            "config": config.model_dump(),
            "result": result,
            "timestamp": time_module.time(),
        }
        try:
            await storage_instance.save_load_test(entry)
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
        await _state.clear_active_test()


@router.post(
    "/start",
    response_model=StartResponse,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
@limiter.limit("5/minute")
async def start_load_test(request: Request, config: LoadTestConfig, storage=Depends(get_storage)) -> dict[str, Any]:
    """
    Start a new load test with the given configuration.

    - Accepts load test parameters (concurrency, RPS, prompt template, etc.)
    - Returns a test_id to track this specific test run
    - Test runs asynchronously; use /status or /stream to monitor progress
    """
    if await _state.has_running_test():
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

    active_task = asyncio.create_task(_run_test_background(test_id, config, storage))
    await _state.set_active_test(active_task, config)

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
    # Stop the engine
    await load_engine.stop()

    # Cancel the active task if exists
    await _state.cancel_active_test()
    await _state.cancel_sweep_if_running()

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
    active_task, current_config, sweep_result, is_sweeping = await _state.get_status_snapshot()
    is_running = active_task is not None and not active_task.done() and load_engine.status == LoadTestStatus.RUNNING

    return {
        "test_id": test_id,
        "running": is_running,
        "config": current_config,
        "current_result": None,
        "elapsed": load_engine.elapsed,
        "sweep_result": sweep_result.model_dump() if sweep_result else None,
        "is_sweeping": is_sweeping,
    }


@router.post("/sweep", responses={409: {"model": ErrorResponse}})
@limiter.limit("5/minute")
async def start_sweep(request: Request, config: SweepConfig) -> dict[str, Any]:
    """Start a parameter sweep with multiple concurrent loads."""
    if (not await _state.can_start_sweep()) or load_engine.is_sweep_running():
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                error="A load test or sweep is already running.",
                error_type="already_running",
            ).model_dump(),
        )
    await _state.mark_sweep_started()

    if config.model == "auto":
        try:
            config.model = await asyncio.wait_for(resolve_model_name(config.endpoint), timeout=3.0)
        except TimeoutError:
            config.model = os.getenv("VLLM_MODEL", "auto")

    async def run_sweep_task():
        """Background task that executes a sweep load test across concurrency levels."""
        try:
            result = await load_engine.run_sweep(config)
            await _state.set_sweep_result(result)
            await load_engine._broadcast({"type": "sweep_completed", "data": result.model_dump()})
        except asyncio.CancelledError:
            pass
        except (RuntimeError, asyncio.TimeoutError, ValueError) as e:
            logger.error("[Sweep] Error: %s", e)
            await load_engine._broadcast({"type": "sweep_completed", "data": None})
        finally:
            await _state.finish_sweep()

    sweep_task = asyncio.create_task(run_sweep_task())
    await _state.set_sweep_task(sweep_task)

    return {"status": "running", "config": config.model_dump()}


@limiter.exempt
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
        """Async generator that streams load test progress events via SSE."""
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(data)}\n\n"
                    event_type = data.get("type")
                    # During sweep: only break on sweep_completed or stopped
                    # During regular test: break on completed or stopped
                    is_sweeping = await _state.is_sweeping()
                    if is_sweeping:
                        if event_type in ("sweep_completed", "stopped", "error"):
                            break
                    else:
                        if event_type in ("completed", "stopped", "error"):
                            break
                except TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            logger.debug("[SSE] Load test stream client disconnected, cleaning up")
            raise
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
async def get_load_test_history(
    response: Response,
    limit: int = Query(default=10, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    storage=Depends(get_storage),
) -> list[dict[str, Any]]:
    """
    Get list of recent load test runs and their final results.

    - Returns summary of completed tests (test_id, config, final result)
    - Sorted by most recent first
    - Limit/offset parameters control pagination
    """
    try:
        total = await storage.count_load_test_history()
        history = await storage.get_load_test_history(limit=limit, offset=offset)
        if response is not None:
            response.headers["X-Total-Count"] = str(total)
        return history
    except OSError as e:
        logger.warning("[LoadTest] Failed to retrieve history (fail-open): %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="스토리지 조회 실패",
                error_type="storage",
            ).model_dump(),
        ) from e


# ==================== Sweep History CRUD ====================


@router.post(
    "/sweep/save",
    responses={500: {"model": ErrorResponse}},
)
async def save_sweep_result(
    sweep: dict[str, Any],
    storage=Depends(get_storage),
) -> dict[str, str]:
    """Save a completed sweep result. Returns {id: str}."""
    try:
        sweep_id = await storage.save_sweep_result(sweep)
        return {"id": sweep_id}
    except (OSError, sqlite3.OperationalError) as e:
        logger.error("[Sweep] Failed to save sweep result: %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to save sweep result", error_type="storage").model_dump(),
        ) from e


@router.get(
    "/sweep/history",
    responses={500: {"model": ErrorResponse}},
)
async def list_sweep_history(
    response: Response,
    limit: int = 20,
    offset: int = 0,
    storage=Depends(get_storage),
) -> list[dict[str, Any]]:
    """List saved sweep results with pagination. Returns X-Total-Count header."""
    try:
        items, total = await storage.get_sweep_history(limit=limit, offset=offset)
        if response is not None:
            response.headers["X-Total-Count"] = str(total)
        return items
    except (OSError, sqlite3.OperationalError) as e:
        logger.error("[Sweep] Failed to list sweep history: %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to list sweep history", error_type="storage").model_dump(),
        ) from e


@router.get(
    "/sweep/history/{sweep_id}",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_sweep_result(
    sweep_id: str,
    storage=Depends(get_storage),
) -> dict[str, Any]:
    """Get a single saved sweep result by ID."""
    try:
        result = await storage.get_sweep_result(sweep_id)
    except (OSError, sqlite3.OperationalError) as e:
        logger.error("[Sweep] Failed to get sweep result %s: %s", sweep_id, e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to retrieve sweep result", error_type="storage").model_dump(),
        ) from e
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(error=f"Sweep {sweep_id} not found", error_type="not_found").model_dump(),
        )
    return result


@router.delete(
    "/sweep/history/{sweep_id}",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_sweep_result(
    sweep_id: str,
    storage=Depends(get_storage),
) -> dict[str, str]:
    """Delete a saved sweep result by ID."""
    try:
        deleted = await storage.delete_sweep_result(sweep_id)
    except (OSError, sqlite3.OperationalError) as e:
        logger.error("[Sweep] Failed to delete sweep result %s: %s", sweep_id, e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(error="Failed to delete sweep result", error_type="storage").model_dump(),
        ) from e
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(error=f"Sweep {sweep_id} not found", error_type="not_found").model_dump(),
        )
    return {"status": "deleted", "sweep_id": sweep_id}
