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

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from errors import OptimizerError
from routers import alerts, benchmark, load_test, metrics, sla, status, tuner, vllm_config
from routers import config as config_router
from routers.status import check_prometheus_health
from services.rate_limiter import limiter
from services.shared import runtime_config
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

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
    import services.shared as shared_module

    # ── Initialize httpx clients ──
    try:
        ca_bundle = os.environ.get("CA_BUNDLE", "")
        internal_verify = ca_bundle if ca_bundle else False
        external_verify = ca_bundle if ca_bundle else True
        shared_module.internal_client = httpx.AsyncClient(
            verify=internal_verify, timeout=httpx.Timeout(30.0, connect=10.0)
        )
        shared_module.external_client = httpx.AsyncClient(
            verify=external_verify, timeout=httpx.Timeout(30.0, connect=10.0)
        )
        logger.info("[Lifespan] HTTP clients initialized")
    except Exception as e:
        logger.warning("[Lifespan] HTTP client initialization failed (continuing): %s", e)

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

    # ── Startup configuration validation ──
    _required_env = ["VLLM_ENDPOINT", "VLLM_MODEL"]
    _optional_env = ["PROMETHEUS_URL", "K8S_NAMESPACE", "K8S_DEPLOYMENT_NAME"]

    for var in _required_env:
        if not os.getenv(var):
            logger.warning("[config] Required env var %s is not set — some features may not work", var)
        else:
            logger.info("[config] %s configured", var)

    for var in _optional_env:
        if not os.getenv(var):
            logger.info("[config] Optional env var %s not set", var)

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

    # ── Close httpx clients ──
    try:
        import services.shared as shared_module

        if shared_module.internal_client:
            await shared_module.internal_client.aclose()
        if shared_module.external_client:
            await shared_module.external_client.aclose()
        logger.info("[Lifespan] HTTP clients closed")
    except Exception as e:
        logger.debug("[Lifespan] HTTP client close failed (non-critical): %s", e)


app = FastAPI(
    title="vLLM Optimizer API",
    description="Backend API for vLLM performance optimization and load testing",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


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
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(OptimizerError)
async def optimizer_error_handler(request: Request, exc: OptimizerError) -> JSONResponse:
    """Handle OptimizerError and subclasses globally."""
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "message": exc.message,
            "detail": exc.detail,
        },
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
@limiter.exempt
async def health_check(request: Request) -> dict[str, Any] | JSONResponse:
    """Health check with dependency validation.
    Query param: deep=1 enables full connectivity checks (slow)."""
    health: dict[str, Any] = {"status": "healthy", "cr_type": runtime_config.cr_type, "dependencies": {}}
    deep_check = request.query_params.get("deep") == "1"

    health["timestamp"] = time.time()

    if deep_check:
        try:
            prom_ok = await check_prometheus_health()
            health["dependencies"]["prometheus"] = "healthy" if prom_ok else "unhealthy"
        except Exception:
            health["dependencies"]["prometheus"] = "unhealthy"

        try:
            from kubernetes import client as k8s_client
            from kubernetes import config as k8s_config

            k8s_config.load_incluster_config()
            v1 = k8s_client.CoreV1Api()
            v1.list_namespaced_pod(namespace=os.getenv("POD_NAMESPACE", "default"), limit=1)
            health["dependencies"]["kubernetes"] = "healthy"
        except Exception:
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
