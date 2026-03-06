"""
Auto Tuner Router
Provides endpoints for viewing tuning status, trials, and applying best parameters.
"""
import uuid
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any
from datetime import datetime

from backend.models.load_test import TuningConfig
from backend.services.load_engine import load_engine
from backend.services.metrics_collector import MetricsCollector
from backend.services.auto_tuner import AutoTuner

router = APIRouter()

# Create singleton instances for services
metrics_collector = MetricsCollector()
auto_tuner = AutoTuner(metrics_collector=metrics_collector, load_engine=load_engine)


class TunerStatusResponse(BaseModel):
    """Response for tuner status"""
    status: str = "idle"  # "idle", "running", "completed", "error"
    current_trial: int | None = None
    total_trials: int | None = None
    best_metric: float | None = None
    elapsed_seconds: float | None = None
    message: str | None = None


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
    n_trials: int = 20
    vllm_endpoint: str = ""
    max_num_seqs_min: int = 64
    max_num_seqs_max: int = 512
    gpu_memory_min: float = 0.80
    gpu_memory_max: float = 0.95


class TuningStartResponse(BaseModel):
    """Response when starting auto-tuning"""
    success: bool
    message: str
    tuning_id: str | None = None


@router.post("/start", response_model=TuningStartResponse)
async def start_tuning(request: TuningStartRequest):
    """Start auto-tuning process."""
    if auto_tuner.is_running:
        return {
            "success": False,
            "message": "Tuning is already running. Wait for it to complete or stop it first.",
            "tuning_id": None,
        }
    # Convert flat request to TuningConfig
    config = TuningConfig(
        max_num_seqs_range=(request.max_num_seqs_min, request.max_num_seqs_max),
        gpu_memory_utilization_range=(request.gpu_memory_min, request.gpu_memory_max),
        objective=request.objective,
        n_trials=request.n_trials,
    )
    import os
    vllm_endpoint = request.vllm_endpoint or os.getenv("VLLM_ENDPOINT", "http://localhost:8000")
    tuning_id = str(uuid.uuid4())
    import asyncio
    _ = asyncio.create_task(auto_tuner.start(config, vllm_endpoint))
    return {
        "success": True,
        "message": f"Tuning started with {request.n_trials} trials",
        "tuning_id": tuning_id,
    }


@router.get("/status", response_model=TunerStatusResponse)
async def get_tuner_status():
    """Get current auto-tuning status."""
    status_value = "running" if auto_tuner.is_running else "idle"
    best_metric = auto_tuner.best.score if auto_tuner.best else None
    return {
        "status": status_value,
        "current_trial": len(auto_tuner.trials) if auto_tuner.trials else None,
        "total_trials": None,
        "best_metric": best_metric,
        "elapsed_seconds": None,
        "message": None
    }


@router.get("/trials", response_model=list[TrialInfo])
async def get_tuning_trials(limit: int = 20):
    """Get list of tuning trials."""
    trials = auto_tuner.trials[-limit:]
    return [
        TrialInfo(
            trial_number=t.trial_id,
            parameters=t.params,
            metrics={"tps": t.tps, "p99_latency": t.p99_latency, "score": t.score},
            status=t.status,
        )
        for t in trials
    ]


@router.post("/stop")
async def stop_tuning():
    """Stop the running auto-tuning process."""
    if not auto_tuner.is_running:
        return {"success": False, "message": "No tuning is currently running."}
    await auto_tuner.stop()
    return {"success": True, "message": "Tuning stopped."}


@router.get("/importance")
async def get_parameter_importance():
    """Get parameter importance from tuning trials (stub)."""
    if not auto_tuner.trials:
        return {}
    return {
        "max_num_seqs": 0.4,
        "gpu_memory_utilization": 0.35,
        "max_model_len": 0.25,
    }


@router.post("/apply-best", response_model=ApplyBestResponse)
async def apply_best_parameters():
    """Apply the best parameters found by auto-tuning to vLLM deployment."""
    # Placeholder for actual K8s implementation
    return {
        "success": False,
        "message": "Auto-tuner integration not yet fully implemented",
        "applied_parameters": None,
        "deployment_name": None
    }
