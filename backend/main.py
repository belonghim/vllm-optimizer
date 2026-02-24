"""
FastAPI Application Entry Point

This module creates the main FastAPI app with CORS middleware
and mounts placeholder routers for the vLLM optimizer backend.
"""

from fastapi import FastAPI
from backend.services.metrics_collector import MetricsCollector
import asyncio
import asyncio
from fastapi.responses import JSONResponse
from typing import Optional
import uuid
import time
from backend.models.load_test import LoadTestConfig, LoadTestResult, LatencyStats, TpsStats, TuningConfig, Benchmark
from fastapi.middleware.cors import CORSMiddleware

# Create FastAPI app
_metrics_collector = None
_metrics_collector_task = None

app = FastAPI(
    title="vLLM Optimizer API",
    description="Backend API for vLLM performance optimization and load testing",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

from fastapi.responses import PlainTextResponse


# Load optional startup shim for MetricsCollector (Dev-friendly)
try:
    from backend.startup_metrics_shim import register
    register(app)
except Exception as e:
    print("Startup shim not loaded:", e)

# Configure CORS to allow frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Create React App
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Placeholder router imports
# These will be implemented in subsequent tasks (T6-T9)
try:
     from backend.routers import load_test, metrics, benchmark, tuner
except ImportError:
    # If routers don't exist yet, create minimal placeholders
    # Note: prefix is added in include_router, not here, to avoid double-prefixes
    from fastapi import APIRouter

    load_test = APIRouter(tags=["load_test"])
    metrics = APIRouter(tags=["metrics"])
    benchmark = APIRouter(tags=["benchmark"])
    tuner = APIRouter(tags=["tuner"])

    # In-memory stores for simple endpoints used by tests
    _benchmark_store = {}
    _benchmark_next_id = 1

    @load_test.post("/start")
    async def start_load_test(config: LoadTestConfig):
        return {
            "test_id": str(uuid.uuid4()),
            "status": "started",
            "message": "Load test started",
            "config": config.model_dump(),
        }

    @load_test.get("/status")
    async def get_load_test_status(test_id: Optional[str] = None):
        return {
            "test_id": test_id,
            "running": False,
            "config": None,
            "current_result": None,
            "elapsed": 0.0,
        }

    @load_test.get("/history")
    async def get_load_test_history(limit: int = 10):
        return []

    @metrics.get("/latest")
    async def get_latest_metrics():
        import time
        ts = int(time.time())
        return {
            "timestamp": ts,
            "tps": 0.0,
            "latency_mean": 0.0,
            "latency_p99": 0.0,
            "ttft_mean": 0.0,
            "ttft_p99": 0.0,
            "kv_cache": 0.0,
            "kv_hit_rate": 0.0,
            "running": 0,
            "waiting": 0,
            "gpu_mem_used": 0.0,
            "gpu_mem_total": 0.0,
            "gpu_util": 0.0,
            "pods": 0,
            "pods_ready": 0,
        }

    @metrics.get("/history")
    async def get_metrics_history(last_n: int = 60):
        return []

    @benchmark.get("/list")
    async def list_benchmarks():
        return list(_benchmark_store.values())

    @benchmark.post("/save")
    async def save_benchmark(payload: dict):
        global _benchmark_next_id
        bid = _benchmark_next_id
        _benchmark_store[bid] = {
            "id": bid,
            "name": payload.get("name"),
            "timestamp": __import__("time").time(),
            "config": payload.get("config"),
            "result": payload.get("result"),
        }
        _benchmark_next_id += 1
        return _benchmark_store[bid]

    @benchmark.get("/{benchmark_id}")
    async def get_benchmark(benchmark_id: int):
        item = _benchmark_store.get(benchmark_id)
        if item is None:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return item

    @benchmark.delete("/{benchmark_id}")
    async def delete_benchmark(benchmark_id: int):
        if benchmark_id in _benchmark_store:
            del _benchmark_store[benchmark_id]
            return {"status": "deleted"}
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    @tuner.get("/status")
    async def get_tuner_status():
        return {"status": "idle"}

    @tuner.get("/trials")
    async def get_tuning_trials(limit: int = 20):
        return []

    @tuner.post("/start")
    async def start_tuning(request: dict):
        return {"success": True, "message": "Tuning started", "tuning_id": str(uuid.uuid4())}

    @tuner.post("/apply-best")
    async def apply_best_parameters():
        return {
            "success": False,
            "message": "Auto-tuner integration not yet implemented",
            "applied_parameters": None,
            "deployment_name": None
        }

# Mount routers under /api prefix with route-specific paths
# Note: routers are imported directly as APIRouter instances, not modules
app.include_router(load_test, prefix="/api/load_test", tags=["load_test"])
app.include_router(metrics, prefix="/api/metrics", tags=["metrics"])
app.include_router(benchmark, prefix="/api/benchmark", tags=["benchmark"])
app.include_router(tuner, prefix="/api/tuner", tags=["tuner"])


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint for readiness probes."""
    return {"status": "healthy", "service": "vllm-optimizer"}


@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API information."""
    return {
        "message": "vLLM Optimizer API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "load_test": "/api/load_test",
            "metrics": "/api/metrics",
            "benchmark": "/api/benchmark",
            "tuner": "/api/tuner"
        }
    }
