"""
Auto Tuner Router
Provides endpoints for viewing tuning status, trials, and applying best parameters.
"""
import asyncio
import logging
import json
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, Optional, List
from datetime import datetime

from models.load_test import ErrorResponse, TuningConfig
from services.shared import multi_target_collector, load_engine
from services.auto_tuner import AutoTuner
from services.shared import storage

logger = logging.getLogger(__name__)
router = APIRouter()

auto_tuner = AutoTuner(metrics_collector=multi_target_collector, load_engine=load_engine)


class TunerStatusResponse(BaseModel):
    """Response for tuner status"""
    status: str = "idle"  # "idle", "running", "completed", "error"
    current_trial: int | None = None
    total_trials: int | None = None
    best_metric: float | None = None
    elapsed_seconds: float | None = None
    message: str | None = None
    wait_metrics: dict[str, Any] | None = None


class TrialInfo(BaseModel):
    """Information about a single tuning trial"""
    trial_number: int
    parameters: dict[str, Any]
    metrics: dict[str, float]
    status: str  # "running", "completed", "failed"
    timestamp: datetime | None = None


class ApplyBestResponse(BaseModel):
    """Response when applying best parameters"""
    success: bool
    message: str
    applied_parameters: dict[str, Any] | None = None
    deployment_name: str | None = None


class TuningStartRequest(BaseModel):
    """Request to start auto-tuning (flat schema matching frontend)"""
    objective: str = "balanced"
    n_trials: int = 10
    eval_requests: int = 100
    vllm_endpoint: str = ""
    max_num_seqs_min: int = 64
    max_num_seqs_max: int = 512
    gpu_memory_min: float = 0.80
    gpu_memory_max: float = 0.95
    max_model_len_min: int = 2048
    max_model_len_max: int = 8192
    # Expanded tuning controls
    max_num_batched_tokens_min: int = 256
    max_num_batched_tokens_max: int = 2048
    block_size_options: list[int] = [8, 16, 32]
    include_swap_space: bool = False
    swap_space_min: float = 1.0
    swap_space_max: float = 8.0
    eval_concurrency: int = 16
    eval_rps: int = 20


class TuningStartResponse(BaseModel):
    """Response when starting auto-tuning"""
    success: bool
    message: str
    tuning_id: str | None = None


class BestTrialInfo(BaseModel):
    """Best trial info for frontend"""
    params: dict[str, Any]
    tps: float
    p99_latency: float


class TunerStatusFrontendResponse(BaseModel):
    """Frontend-compatible tuner status response"""
    running: bool
    trials_completed: int = 0
    best: Optional[BestTrialInfo] = None
    status: str | None = None
    best_score_history: list[float] = []
    pareto_front_size: int | None = None
    last_rollback_trial: int | None = None


class TrialFrontendInfo(BaseModel):
    """Frontend-compatible trial info"""
    id: int
    tps: float
    p99_latency: float  # milliseconds
    params: dict[str, Any]
    score: float
    status: str
    is_pareto_optimal: bool = False
    pruned: bool = False


class TunerAllResponse(BaseModel):
    """Combined response for status, trials, and importance"""
    status: TunerStatusFrontendResponse
    trials: list[TrialFrontendInfo]
    importance: dict[str, Any]


@router.post("/start", response_model=TuningStartResponse)
async def start_tuning(request: TuningStartRequest) -> dict[str, Any]:
    """Start auto-tuning process."""
    if auto_tuner.is_running:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                error="Tuning is already running. Wait for it to complete or stop it first.",
                error_type="already_running",
            ).model_dump(),
        )
    try:
        await storage.clear_trials()
    except Exception as e:
        logger.warning("[Tuner] Failed to clear trials from storage before new session: %s", e)
    config = TuningConfig(
        max_num_seqs_range=(request.max_num_seqs_min, request.max_num_seqs_max),
        gpu_memory_utilization_range=(request.gpu_memory_min, request.gpu_memory_max),
        max_model_len_range=(request.max_model_len_min, request.max_model_len_max),
        max_num_batched_tokens_range=(request.max_num_batched_tokens_min, request.max_num_batched_tokens_max),
        block_size_options=request.block_size_options,
        include_swap_space=request.include_swap_space,
        swap_space_range=(request.swap_space_min, request.swap_space_max),
        eval_concurrency=request.eval_concurrency,
        eval_rps=request.eval_rps,
        eval_requests=request.eval_requests,
        objective=request.objective,
        n_trials=request.n_trials,
    )
    import os
    vllm_endpoint = request.vllm_endpoint or os.getenv("VLLM_ENDPOINT", "http://localhost:8000")

    try:
        preflight = await auto_tuner._preflight_check()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=f"Preflight check failed: {exc}",
                error_type="preflight_error",
            ).model_dump(),
        )
    if not preflight.get("success"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=preflight.get("error", "Preflight check failed"),
                error_type=preflight.get("error_type", "preflight_error"),
            ).model_dump(),
        )

    tuning_id = str(uuid.uuid4())
    auto_tuner._current_task = asyncio.create_task(auto_tuner.start(config, vllm_endpoint, skip_preflight=True))
    auto_tuner._current_task.add_done_callback(
        lambda t: logger.error("[AutoTuner] Task failed: %s", t.exception()) if t.exception() else None
    )
    return {
        "success": True,
        "message": f"Tuning started with {request.n_trials} trials",
        "tuning_id": tuning_id,
    }


@router.get("/status", response_model=TunerStatusFrontendResponse)
async def get_tuner_status() -> TunerStatusFrontendResponse:
    """Get current auto-tuning status."""
    # Frontend-friendly status payload
    best_info = None
    if auto_tuner.best is not None:
        best_info = BestTrialInfo(
            params=auto_tuner.best.params,
            tps=auto_tuner.best.tps,
            p99_latency=auto_tuner.best.p99_latency * 1000,
        )
    status_value = "running" if auto_tuner.is_running else "idle"
    return TunerStatusFrontendResponse(
        running=auto_tuner.is_running,
        trials_completed=len(auto_tuner.trials),
        best=best_info,
        status=status_value,
        best_score_history=getattr(auto_tuner, "_best_score_history", []),
        pareto_front_size=getattr(auto_tuner, "_pareto_front_size", None),
        last_rollback_trial=auto_tuner._last_rollback_trial,
    )


@router.get("/trials", response_model=list[TrialFrontendInfo])
async def get_tuning_trials(limit: int = 20) -> list[TrialFrontendInfo]:
    """Get list of tuning trials."""
    try:
        all_trials = await storage.get_trials()
        if not all_trials:
            all_trials = auto_tuner.trials
    except Exception:
        all_trials = auto_tuner.trials
    trials = all_trials[-limit:]
    return [
        TrialFrontendInfo(
            id=t.trial_id,
            tps=t.tps,
            p99_latency=t.p99_latency * 1000,
            params=t.params,
            score=t.score,
            status=t.status,
            is_pareto_optimal=getattr(t, "is_pareto_optimal", False),
            pruned=getattr(t, "pruned", False),
        )
        for t in trials
    ]


@router.post("/stop")
async def stop_tuning() -> dict[str, Any]:
    """Stop the running auto-tuning process."""
    return await auto_tuner.stop()

@router.get("/stream")
async def stream_tuner_events() -> StreamingResponse:
    """Stream tuning events via Server-Sent Events (SSE)."""
    async def event_generator():
        q = await auto_tuner.subscribe()
        try:
            yield f"data: {json.dumps({'type': 'connected', 'data': {'running': auto_tuner.is_running}})}\n\n"
            
            keepalive_count = 0
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    
                    if event.get("type") == "tuning_complete":
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    keepalive_count += 1
                    if keepalive_count > 20:  # Max 10 minutes of keepalive
                        break
        except asyncio.CancelledError:
            pass
        finally:
            await auto_tuner.unsubscribe(q)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/importance")
async def get_parameter_importance() -> dict[str, Any]:
    """Get parameter importance from tuning trials (actual implementation)."""
    # Use the AutoTuner's implementation which computes importances via Optuna
    # FAnova if enough trials have been run. Returns {} when not enough data.
    return await auto_tuner.get_importance()


@router.get("/all", response_model=TunerAllResponse)
async def get_tuner_all() -> TunerAllResponse:
    """Get combined tuner state: status, trials, and importance in one request."""
    status = await get_tuner_status()
    trials = await get_tuning_trials()
    importance = await get_parameter_importance()
    return TunerAllResponse(status=status, trials=trials, importance=importance)


@router.post("/apply-best", response_model=ApplyBestResponse)
async def apply_best_parameters() -> ApplyBestResponse:
    """Apply the best parameters found by auto-tuning to vLLM deployment."""
    import os
    # If no best trial is available yet
    if auto_tuner.best is None:
        return ApplyBestResponse(
            success=False,
            message="No best trial available. Run tuning first.",
            applied_parameters=None,
            deployment_name=None,
        )
    # If tuning is currently running, do not apply
    if auto_tuner.is_running:
        return ApplyBestResponse(
            success=False,
            message="Tuning is in progress. Wait for completion or stop first.",
            applied_parameters=None,
            deployment_name=None,
        )

    result = await auto_tuner._apply_params(auto_tuner.best.params)
    if isinstance(result, dict) and result.get("success"):
        return ApplyBestResponse(
            success=True,
            message="Best parameters applied successfully.",
            applied_parameters=auto_tuner.best.params,
            deployment_name=os.getenv("VLLM_DEPLOYMENT_NAME", "llm-ov"),
        )
    return ApplyBestResponse(
        success=False,
        message=result.get("error", "Failed to apply parameters."),
        applied_parameters=None,
        deployment_name=None,
    )
