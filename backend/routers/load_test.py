"""
Load Test Router
Provides endpoints for starting, stopping, and monitoring load tests.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json
import asyncio
import os
import uuid
import logging
import time as time_module

from models.load_test import (
    ErrorResponse,
    LoadTestConfig,
    LoadTestResult,
    RequestResult,
    LatencyStats,
    TpsStats,
)

from services.load_engine import load_engine, LoadTestStatus
from services.model_resolver import resolve_model_name
from services.shared import storage

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory state for active test (in production, use proper state management)
_active_test_task: Optional[asyncio.Task[Any]] = None
_current_config: Optional[LoadTestConfig] = None
_test_lock = asyncio.Lock()


# Simple response models for start/stop
class StartResponse(BaseModel):
    """Response when starting a load test"""
    test_id: str
    status: str
    message: str
    config: Dict[str, Any]


class StopResponse(BaseModel):
    """Response when stopping a load test"""
    status: str
    test_id: str
    message: str


class StatusResponse(BaseModel):
    """Response for load test status"""
    test_id: Optional[str] = None
    running: bool = False
    config: Optional[LoadTestConfig] = None
    current_result: Optional[LoadTestResult] = None
    elapsed: float = 0.0


@router.post("/start", response_model=StartResponse)
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
            config.model = await asyncio.wait_for(
                resolve_model_name(config.endpoint), timeout=3.0
            )
        except asyncio.TimeoutError:
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
            except Exception as e:
                logger.warning("[LoadTest] Failed to persist history (fail-open): %s", e)
        except Exception as e:  # intentional: non-critical
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
async def stop_load_test(test_id: Optional[str] = None) -> dict[str, Any]:
    """
    Stop a running load test.

    - Requires test_id from /start response
    - Gracefully stops all worker tasks
    - Final results will be available via /status
    """
    global _active_test_task
    
    # Stop the engine
    await load_engine.stop()
    
    # Cancel the active task if exists
    if _active_test_task and not _active_test_task.done():
        _active_test_task.cancel()
        _active_test_task = None
    
    return {
        "status": "stopped",
        "test_id": test_id,
        "message": "Load test stopped successfully",
    }


@router.get("/status", response_model=StatusResponse)
async def get_load_test_status(test_id: Optional[str] = None) -> dict[str, Any]:
    """
    Get current status and intermediate results of a load test.

    - If test_id is provided, returns status for that specific test
    - If no test_id, returns status of the most recent test (if any)
    - Includes elapsed time, success/failed counts, and current latency/TPS stats
    """
    global _active_test_task, _current_config
    
    is_running = (
        _active_test_task is not None 
        and not _active_test_task.done()
        and load_engine.status == LoadTestStatus.RUNNING
    )
    
    return {
        "test_id": test_id,
        "running": is_running,
        "config": _current_config,
        "current_result": None,
        "elapsed": load_engine.elapsed,
    }


@router.get("/stream")
async def stream_load_test_results(test_id: Optional[str] = None) -> StreamingResponse:
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
                    if data.get("type") in ("completed", "stopped"):
                        break
                except asyncio.TimeoutError:
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


@router.get("/history")
async def get_load_test_history(limit: int = 10) -> list[dict[str, Any]]:
    """
    Get list of recent load test runs and their final results.

    - Returns summary of completed tests (test_id, config, final result)
    - Sorted by most recent first
    - Limit parameter controls number of results returned
    """
    try:
        return await storage.get_load_test_history(limit=limit)
    except Exception as e:
        logger.warning("[LoadTest] Failed to retrieve history (fail-open): %s", e)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="스토리지 조회 실패",
                error_type="storage",
            ).model_dump(),
        )
