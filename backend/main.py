"""
FastAPI Application Entry Point

This module creates the main FastAPI app with CORS middleware
and mounts placeholder routers for the vLLM optimizer backend.
"""

import logging
import os
import time
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from kubernetes import client
from kubernetes import config as k8s_config
from routers import alerts, benchmark, load_test, metrics, sla, status, tuner, vllm_config
from routers import config as config_router

# ── Logging Configuration ──
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# Load optional startup shim for MetricsCollector (Dev-friendly)
try:
    import startup_metrics_shim as startup_metrics_shim_module

    _create_lifespan = startup_metrics_shim_module.create_lifespan
    register_shim = startup_metrics_shim_module.register
except Exception as e:  # intentional: fail-open
    logger.debug("Startup shim not loaded: %s", e)

    def register_shim(app: FastAPI) -> None:
        return None

    def _create_lifespan(app):
        @asynccontextmanager
        async def _noop_lifespan(app):
            yield

        return _noop_lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Storage initialization (fail-open) ──
    try:
        from services.shared import storage

        await storage.initialize()
        logger.info("[Lifespan] Storage initialized")
    except Exception as e:
        logger.warning("[Lifespan] Storage initialization failed (continuing): %s", e)

    # ── Detect interrupted runs from previous lifecycle ──
    try:
        from routers.status import set_interrupted_runs
        from services.shared import storage as _storage

        interrupted = await _storage.get_interrupted_runs()
        if interrupted:
            logger.warning("[Lifespan] Detected %d interrupted run(s) from previous lifecycle", len(interrupted))
            await set_interrupted_runs(interrupted)
    except Exception as e:
        logger.warning("[Lifespan] Failed to detect interrupted runs (continuing): %s", e)

    try:
        from services.shared import storage_health_monitor

        storage_health_monitor.start()
        logger.info("[Lifespan] Storage health monitor started")
    except Exception as e:
        logger.warning("[Lifespan] Storage health monitor start failed (continuing): %s", e)

    async with _create_lifespan(app)(app):
        yield

    # ── Storage health monitor shutdown (fail-open) ──
    try:
        from services.shared import storage_health_monitor

        storage_health_monitor.stop()
        logger.info("[Lifespan] Storage health monitor stopped")
    except Exception as e:
        logger.debug("[Lifespan] Storage health monitor stop failed (non-critical): %s", e)

    # ── Cleanup running_state on shutdown (fail-open) ──
    try:
        from services.shared import storage as _shutdown_storage

        running_rows = await _shutdown_storage.get_all_running()
        for row in running_rows:
            with suppress(Exception):
                await _shutdown_storage.clear_running(row["id"])
        if running_rows:
            logger.info("[Lifespan] Cleared %d running_state row(s) on shutdown", len(running_rows))
    except Exception as e:
        logger.debug("[Lifespan] running_state shutdown cleanup failed (non-critical): %s", e)

    # ── Storage shutdown (fail-open) ──
    try:
        from services.shared import storage

        await storage.close()
        logger.info("[Lifespan] Storage closed")
    except Exception as e:
        logger.debug("[Lifespan] Storage close failed (non-critical): %s", e)


app = FastAPI(
    title="vLLM Optimizer API",
    description="Backend API for vLLM performance optimization and load testing",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
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
            with open(token_path) as f:
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
    except Exception:  # intentional: non-critical
        return False


try:
    register_shim(app)
except Exception as e:  # intentional: fail-open
    logger.debug("Startup shim route registration failed: %s", e)

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

# Mount routers under /api prefix with route-specific paths
# Note: routers are imported directly as APIRouter instances, not modules
app.include_router(load_test, prefix="/api/load_test", tags=["load_test"])
app.include_router(metrics, prefix="/api/metrics", tags=["metrics"])
app.include_router(benchmark, prefix="/api/benchmark", tags=["benchmark"])
app.include_router(tuner, prefix="/api/tuner", tags=["tuner"])
app.include_router(vllm_config, prefix="/api/vllm-config", tags=["vllm-config"])
app.include_router(config_router)
app.include_router(status, prefix="/api", tags=["status"])
app.include_router(sla, prefix="/api/sla", tags=["sla"])
app.include_router(alerts, prefix="/api/alerts", tags=["alerts"])


@app.get("/health", tags=["health"], response_model=None)
async def health_check(request: Request) -> dict[str, Any] | JSONResponse:
    """Health check with dependency validation.
    Query param: deep=1 enables full connectivity checks (slow)."""
    health: dict[str, Any] = {"status": "healthy", "dependencies": {}}
    deep_check = request.query_params.get("deep") == "1"

    health["timestamp"] = time.time()

    if deep_check:
        try:
            prom_ok = await check_prometheus_health()
            health["dependencies"]["prometheus"] = "healthy" if prom_ok else "unhealthy"
        except Exception:  # intentional: non-critical
            health["dependencies"]["prometheus"] = "unhealthy"

        try:
            k8s_config.load_incluster_config()
            v1 = client.CoreV1Api()
            v1.list_namespaced_pod(namespace=os.getenv("POD_NAMESPACE", "default"), limit=1)
            health["dependencies"]["kubernetes"] = "healthy"
        except Exception:  # intentional: non-critical
            health["dependencies"]["kubernetes"] = "unhealthy"

    all_healthy = all(v == "healthy" for v in health["dependencies"].values())
    if not all_healthy:
        health["status"] = "unhealthy"
        return JSONResponse(status_code=503, content=health)

    return health


@app.get("/", tags=["root"])
async def root() -> dict[str, Any]:
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
            "tuner": "/api/tuner",
        },
    }
