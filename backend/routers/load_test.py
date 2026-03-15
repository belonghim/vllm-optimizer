"""
Load Test Router
Provides endpoints for starting, stopping, and monitoring load tests.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import asyncio
import uuid
import logging
from collections import deque
import time as time_module

from models.load_test import (
    LoadTestConfig,
    LoadTestResult,
    RequestResult,
    LatencyStats,
    TpsStats,
)

from services.load_engine import load_engine, LoadTestStatus
from services.model_resolver import resolve_model_name

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory state for active test (in production, use proper state management)
_active_test_task: Optional[asyncio.Task] = None
_current_config: Optional[LoadTestConfig] = None

# In-memory history store (max 100 entries, no persistence)
_test_history: deque = deque(maxlen=100)


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
async def start_load_test(config: LoadTestConfig):
    """
    Start a new load test with the given configuration.

    - Accepts load test parameters (concurrency, RPS, prompt template, etc.)
    - Returns a test_id to track this specific test run
    - Test runs asynchronously; use /status or /stream to monitor progress
    """
    global _active_test_task, _current_config
    
    test_id = str(uuid.uuid4())

    if config.model == "auto":
        config.model = await resolve_model_name(config.endpoint)

    # Run test in background task
    async def run_test():
        global _active_test_task
        try:
            result = await load_engine.run(config)
            _test_history.appendleft({
                "test_id": test_id,
                "config": config.model_dump(),
                "result": result,
                "timestamp": time_module.time(),
            })
        except Exception as e:
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
async def stop_load_test(test_id: Optional[str] = None):
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
async def get_load_test_status(test_id: Optional[str] = None):
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
async def stream_load_test_results(test_id: Optional[str] = None):
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
async def get_load_test_history(limit: int = 10):
    """
    Get list of recent load test runs and their final results.

    - Returns summary of completed tests (test_id, config, final result)
    - Sorted by most recent first
    - Limit parameter controls number of results returned
    """
    return list(_test_history)[:limit]
