"""
Auto Tuner Router
Provides endpoints for viewing tuning status, trials, and applying best parameters.
"""
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..models.load_test import TuningConfig, TuningTrial
from ..services.load_engine import load_engine
from ..services.metrics_collector import MetricsCollector
from ..services.auto_tuner import AutoTuner

router = APIRouter()

# Create singleton instances for services
metrics_collector = MetricsCollector()
auto_tuner = AutoTuner(metrics_collector=metrics_collector, load_engine=load_engine)


class TunerStatusResponse(BaseModel):
    """Response for tuner status"""
    status: str = "idle"  # "idle", "running", "completed", "error"
    current_trial: Optional[int] = None
    total_trials: Optional[int] = None
    best_metric: Optional[float] = None
    elapsed_seconds: Optional[float] = None
    message: Optional[str] = None


class TrialInfo(BaseModel):
    """Information about a single tuning trial"""
    trial_number: int
    parameters: Dict[str, Any]
    metrics: Dict[str, float]
    status: str  # "running", "completed", "failed"
    timestamp: Optional[datetime] = None


class ApplyBestResponse(BaseModel):
    """Response when applying best parameters"""
    success: bool
    message: str
    applied_parameters: Optional[Dict[str, Any]] = None
    deployment_name: Optional[str] = None


class TuningStartRequest(BaseModel):
    """Request to start auto-tuning"""
    config: TuningConfig
    vllm_endpoint: str = "http://localhost:8000"


class TuningStartResponse(BaseModel):
    """Response when starting auto-tuning"""
    success: bool
    message: str
    tuning_id: Optional[str] = None


@router.post("/start", response_model=TuningStartResponse)
async def start_tuning(request: TuningStartRequest):
    """Start auto-tuning process."""
    if auto_tuner.is_running:
        return {
            "success": False,
            "message": "Tuning is already running. Wait for it to complete or stop it first.",
            "tuning_id": None,
        }
    tuning_id = str(uuid.uuid4())
    import asyncio
    asyncio.create_task(auto_tuner.start(request.config, request.vllm_endpoint))
    return {
        "success": True,
        "message": f"Tuning started with {request.config.n_trials} trials",
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


@router.get("/trials", response_model=List[TrialInfo])
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
