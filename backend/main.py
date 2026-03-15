"""
FastAPI Application Entry Point

This module creates the main FastAPI app with CORS middleware
and mounts placeholder routers for the vLLM optimizer backend.
"""

import logging
import os
import time
import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from kubernetes import config, client



# ── Logging Configuration ──
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="vLLM Optimizer API",
    description="Backend API for vLLM performance optimization and load testing",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Helper function for Prometheus connectivity check
async def check_prometheus_health() -> bool:
    """Check Prometheus/Thanos connectivity with a lightweight query."""
    try:
        import httpx
        
        thanos_url = os.getenv("PROMETHEUS_URL", "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091")
        
        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        token = None
        if os.path.exists(token_path):
            with open(token_path, 'r') as f:
                token = f.read().strip()
        
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        
        query = "1"
        async with httpx.AsyncClient(timeout=3, verify=False) as client:
            resp = await client.get(
                f"{thanos_url}/api/v1/query",
                headers=headers,
                params={"query": query},
            )
            return resp.status_code == 200
    except Exception:
        return False




# Load optional startup shim for MetricsCollector (Dev-friendly)
try:
    from startup_metrics_shim import register
    register(app)
except Exception as e:
    logger.debug("Startup shim not loaded: %s", e)

# Configure CORS — read from ALLOWED_ORIGINS env var (comma-separated), fall back to localhost defaults
_default_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
_raw = os.getenv("ALLOWED_ORIGINS", "")
_origins = [o.strip() for o in _raw.split(",") if o.strip()] if _raw else _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers import load_test, metrics, benchmark, tuner, vllm_config
from services.model_resolver import resolve_model_name

# Mount routers under /api prefix with route-specific paths
# Note: routers are imported directly as APIRouter instances, not modules
app.include_router(load_test, prefix="/api/load_test", tags=["load_test"])
app.include_router(metrics, prefix="/api/metrics", tags=["metrics"])
app.include_router(benchmark, prefix="/api/benchmark", tags=["benchmark"])
app.include_router(tuner, prefix="/api/tuner", tags=["tuner"])
app.include_router(vllm_config, prefix="/api/vllm-config", tags=["vllm-config"])


@app.get("/health", tags=["health"])
async def health_check(request: Request):
    """Health check with dependency validation.
    Query param: deep=1 enables full connectivity checks (slow)."""
    health = {"status": "healthy", "dependencies": {}}
    deep_check = request.query_params.get("deep") == "1"

    health["timestamp"] = time.time()

    if deep_check:
        try:
            prom_ok = await check_prometheus_health()
            health["dependencies"]["prometheus"] = "healthy" if prom_ok else "unhealthy"
        except Exception:
            health["dependencies"]["prometheus"] = "unhealthy"

        try:
            config.load_incluster_config()
            v1 = client.CoreV1Api()
            v1.list_namespaced_pod(namespace=os.getenv("POD_NAMESPACE", "default"), limit=1)
            health["dependencies"]["kubernetes"] = "healthy"
        except Exception:
            health["dependencies"]["kubernetes"] = "unhealthy"

    all_healthy = all(v == "healthy" for v in health["dependencies"].values())
    if not all_healthy:
        health["status"] = "unhealthy"
        return JSONResponse(status_code=503, content=health)

    return health





@app.get("/api/config", tags=["config"])
async def get_frontend_config():
    """Return server-side configuration for frontend defaults."""
    endpoint = os.getenv("VLLM_ENDPOINT", "http://localhost:8000")
    model_name = os.getenv("VLLM_MODEL", "auto")
    try:
        resolved = await asyncio.wait_for(
            resolve_model_name(endpoint), timeout=3.0
        )
    except Exception:
        resolved = model_name
    return {
        "vllm_endpoint": endpoint,
        "vllm_namespace": os.getenv("VLLM_NAMESPACE", "vllm"),
        "vllm_model_name": model_name,
        "resolved_model_name": resolved,
    }


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
