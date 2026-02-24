"""
FastAPI Application Entry Point

This module creates the main FastAPI app with CORS middleware
and mounts placeholder routers for the vLLM optimizer backend.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create FastAPI app
app = FastAPI(
    title="vLLM Optimizer API",
    description="Backend API for vLLM performance optimization and load testing",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

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
     from routers import load_test, metrics, benchmark, tuner
except ImportError:
    # If routers don't exist yet, create minimal placeholders
    # Note: prefix is added in include_router, not here, to avoid double-prefixes
    from fastapi import APIRouter

    load_test = APIRouter(tags=["load_test"])
    metrics = APIRouter(tags=["metrics"])
    benchmark = APIRouter(tags=["benchmark"])
    tuner = APIRouter(tags=["tuner"])

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
