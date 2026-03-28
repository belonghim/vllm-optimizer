"""
Metrics Router - vLLM Optimizer API

Provides endpoints for retrieving real-time and historical metrics.
"""

import asyncio
import math
import os
import time as time_mod
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from services.rate_limiter import limiter
from services.retry_helper import with_retry
from models.load_test import (
    BatchMetricsRequest,
    BatchMetricsResponse,
    ErrorResponse,
    MetricsSnapshot,
    TargetedMetricsResponse,
)
from services.shared import multi_target_collector, runtime_config

router = APIRouter()

MAX_HISTORY_POINTS = 1000

PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091",
)

_TIME_RANGE_CONFIG: dict[str, dict[str, int]] = {
    "6h": {"duration": 6 * 3600, "step": 30},
    "24h": {"duration": 24 * 3600, "step": 90},
    "7d": {"duration": 7 * 24 * 3600, "step": 600},
}

_METRIC_FIELD_MAP = {
    "tokens_per_second": "tps",
    "requests_per_second": "rps",
    "mean_ttft_ms": "ttft_mean",
    "p99_ttft_ms": "ttft_p99",
    "mean_e2e_latency_ms": "latency_mean",
    "p99_e2e_latency_ms": "latency_p99",
    "kv_cache_usage_pct": "kv_cache",
    "kv_cache_hit_rate": "kv_hit_rate",
    "running_requests": "running",
    "waiting_requests": "waiting",
    "gpu_memory_used_gb": "gpu_mem_used",
    "gpu_memory_total_gb": "gpu_mem_total",
    "gpu_utilization_pct": "gpu_util",
}


async def _fetch_query_range(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    query: str,
    start: float,
    end: float,
    step: int,
) -> list[tuple[float, float]]:
    try:

        async def _do_get():
            r = await client.get(
                f"{PROMETHEUS_URL}/api/v1/query_range",
                params={"query": query, "start": start, "end": end, "step": step},
                headers=headers,
            )
            r.raise_for_status()
            return r

        response = await with_retry(_do_get, label="thanos-query-range")
        data = response.json()
        if data.get("status") != "success":
            return []
        results = data.get("data", {}).get("result", [])
        if not results:
            return []
        values = results[0].get("values", [])
        parsed: list[tuple[float, float]] = []
        for item in values:
            try:
                ts = float(item[0])
                v = float(item[1])
                if not (math.isnan(v) or math.isinf(v)):
                    parsed.append((ts, v))
            except (ValueError, IndexError):
                pass
        return parsed
    except (httpx.HTTPError, ValueError, KeyError):
        return []


def _build_snapshots_from_ts_data(
    all_timestamps: set[float],
    ts_data: dict[float, dict[str, float]],
) -> list[dict]:
    snapshots = []
    for ts in sorted(all_timestamps):
        d = ts_data[ts]
        snap = MetricsSnapshot(
            timestamp=ts,
            tps=d.get("tps", 0.0),
            rps=d.get("rps", 0.0),
            ttft_mean=d.get("ttft_mean", 0.0),
            ttft_p99=d.get("ttft_p99", 0.0),
            latency_mean=d.get("latency_mean", 0.0),
            latency_p99=d.get("latency_p99", 0.0),
            kv_cache=d.get("kv_cache", 0.0),
            kv_hit_rate=d.get("kv_hit_rate", 0.0),
            running=int(d.get("running", 0)),
            waiting=int(d.get("waiting", 0)),
            gpu_mem_used=d.get("gpu_mem_used", 0.0),
            gpu_mem_total=d.get("gpu_mem_total", 0.0),
            gpu_util=d.get("gpu_util", 0.0),
            pods=0,
            pods_ready=0,
        )
        snapshots.append(snap.model_dump())
    return snapshots


async def _get_history_from_thanos(
    namespace: str,
    is_name: str,
    cr_type: str | None,
    time_range: str,
) -> list[dict]:
    cfg = _TIME_RANGE_CONFIG.get(time_range)
    if not cfg:
        return []

    now = time_mod.time()
    start = now - cfg["duration"]
    step = cfg["step"]

    queries = multi_target_collector._build_target_queries(namespace, is_name, cr_type)
    headers: dict[str, str] = {}
    token = multi_target_collector._token
    if token:
        headers["Authorization"] = f"Bearer {token}"

    field_names = list(queries.keys())
    async with httpx.AsyncClient(verify=False, timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        series_list = await asyncio.gather(
            *[_fetch_query_range(client, headers, queries[f], start, now, step) for f in field_names]
        )

    metric_series: dict[str, list[tuple[float, float]]] = dict(zip(field_names, series_list))

    all_timestamps: set[float] = set()
    for series in metric_series.values():
        for ts, _ in series:
            all_timestamps.add(ts)

    if not all_timestamps:
        return []

    ts_data: dict[float, dict[str, float]] = {ts: {} for ts in all_timestamps}
    for vllm_field, series in metric_series.items():
        snapshot_field = _METRIC_FIELD_MAP.get(vllm_field)
        if not snapshot_field:
            continue
        for ts, value in series:
            ts_data[ts][snapshot_field] = value

    return _build_snapshots_from_ts_data(all_timestamps, ts_data)


def _convert_to_snapshot(vllm_metrics) -> MetricsSnapshot:
    """Convert VLLMMetrics to MetricsSnapshot

    Known limitation: /latest returns 0.0 for idle latency fields;
    /history returns null. This is intentional — /latest shows "last known"
    while /history provides chart-friendly nullable time series.
    """
    if vllm_metrics is None:
        return MetricsSnapshot(
            timestamp=datetime.now(UTC).timestamp(),
            tps=0.0,
            rps=0.0,
            ttft_mean=0.0,
            ttft_p99=0.0,
            latency_mean=0.0,
            latency_p99=0.0,
            kv_cache=0.0,
            kv_hit_rate=0.0,
            running=0,
            waiting=0,
            gpu_mem_used=0.0,
            gpu_mem_total=0.0,
            gpu_util=0.0,
            pods=0,
            pods_ready=0,
        )

    return MetricsSnapshot(
        timestamp=vllm_metrics.timestamp,
        tps=vllm_metrics.tokens_per_second,
        rps=vllm_metrics.requests_per_second,
        ttft_mean=vllm_metrics.mean_ttft_ms,
        ttft_p99=vllm_metrics.p99_ttft_ms,
        latency_mean=vllm_metrics.mean_e2e_latency_ms,
        latency_p99=vllm_metrics.p99_e2e_latency_ms,
        kv_cache=vllm_metrics.kv_cache_usage_pct,
        kv_hit_rate=vllm_metrics.kv_cache_hit_rate,
        running=vllm_metrics.running_requests,
        waiting=vllm_metrics.waiting_requests,
        gpu_mem_used=vllm_metrics.gpu_memory_used_gb,
        gpu_mem_total=vllm_metrics.gpu_memory_total_gb,
        gpu_util=vllm_metrics.gpu_utilization_pct,
        pods=vllm_metrics.pod_count,
        pods_ready=vllm_metrics.pod_ready,
    )


@router.get(
    "/latest",
    responses={
        409: {"model": ErrorResponse},
    },
)
@limiter.limit("120/minute")
async def get_latest_metrics(
    request: Request,
    namespace: str | None = None,
    is_name: str | None = None,
    cr_type: str | None = None,
) -> MetricsSnapshot | TargetedMetricsResponse:
    """
    Get the latest real-time metrics snapshot.

    When namespace and is_name are provided, returns targeted metrics for that
    InferenceService with status-based response.

    Returns current vLLM performance metrics including:
    - TPS (tokens per second)
    - RPS (requests per second)
    - TTFT (time to first token) mean and P99
    - End-to-end latency mean and P99
    - KV cache usage and hit rate
    - GPU memory and utilization
    - Pod status (running/waiting requests, pod count)
    """
    if namespace is not None and is_name is not None:
        registered = await multi_target_collector.register_target(
            namespace, is_name, cr_type=cr_type or runtime_config.cr_type
        )
        if not registered:
            raise HTTPException(
                status_code=409,
                detail=ErrorResponse(
                    error="Max targets reached",
                    error_type="max_targets",
                ).model_dump(),
            )

        vllm_metrics = await multi_target_collector.get_metrics(namespace, is_name)
        has_monitoring_label = multi_target_collector.get_has_monitoring_label(namespace, is_name)

        if vllm_metrics is None:
            return TargetedMetricsResponse(
                status="collecting",
                data=None,
                hasMonitoringLabel=has_monitoring_label,
            )
        return TargetedMetricsResponse(
            status="ready",
            data=_convert_to_snapshot(vllm_metrics),
            hasMonitoringLabel=has_monitoring_label,
        )

    default_namespace = runtime_config.vllm_namespace
    default_is_name = runtime_config.vllm_is_name
    _ = await multi_target_collector.register_target(default_namespace, default_is_name)
    vllm_metrics = await multi_target_collector.get_metrics(default_namespace, default_is_name)
    return _convert_to_snapshot(vllm_metrics)


@router.post("/batch")
@limiter.limit("120/minute")
async def get_batch_metrics(request: Request, body: BatchMetricsRequest) -> BatchMetricsResponse:
    """
    Get latest metrics for multiple targets in a single request.

    Request body contains a list of targets (namespace + inferenceService).
    Response maps each target to its metrics data and status.
    """
    results: dict[str, dict[str, object]] = {}

    for target in body.targets:
        key = f"{target.namespace}/{target.inferenceService}"
        registered = await multi_target_collector.register_target(
            target.namespace, target.inferenceService, cr_type=target.cr_type
        )
        if not registered:
            results[key] = {"data": None, "status": "max_targets_reached"}
            continue

        vllm_metrics = await multi_target_collector.get_metrics(target.namespace, target.inferenceService)
        has_monitoring_label = multi_target_collector.get_has_monitoring_label(
            target.namespace, target.inferenceService
        )

        if body.time_range in _TIME_RANGE_CONFIG:
            history = await _get_history_from_thanos(
                target.namespace, target.inferenceService, target.cr_type, body.time_range
            )
        else:
            target_cache = multi_target_collector._targets.get(key)
            n = min(body.history_points, MAX_HISTORY_POINTS)
            history = (
                [_convert_to_snapshot(m).model_dump() for m in list(target_cache.history)[-n:]] if target_cache else []
            )

        if vllm_metrics is None:
            results[key] = {
                "data": None,
                "status": "collecting",
                "hasMonitoringLabel": has_monitoring_label,
                "history": history,
            }
        else:
            snapshot = _convert_to_snapshot(vllm_metrics)
            results[key] = {
                "data": snapshot.model_dump(),
                "status": "ready",
                "hasMonitoringLabel": has_monitoring_label,
                "history": history,
            }

    return BatchMetricsResponse(results=results)


@router.get("/history", response_model=list[MetricsSnapshot])
@limiter.limit("120/minute")
async def get_metrics_history(
    request: Request,
    last_n: int | None = 60,
    namespace: str | None = None,
    is_name: str | None = None,
) -> list[MetricsSnapshot]:
    """
    Get historical metrics for the last N data points.

    Parameters:
    - **last_n**: Number of historical data points to return (default: 60)
    - **namespace**: Target namespace (optional, for multi-target)
    - **is_name**: Target InferenceService name (optional, for multi-target)

    Returns an array of MetricsSnapshot objects ordered by timestamp ascending.
    Each snapshot contains the same metrics as `/latest` endpoint.
    """
    if namespace is not None and is_name is not None:
        target = multi_target_collector._targets.get(f"{namespace}/{is_name}")
        if target is None:
            return []
        n = last_n if last_n is not None else 60
        history = list(target.history)[-n:]
        return [_convert_to_snapshot(m) for m in history]

    history_dict = multi_target_collector.get_history_dict(last_n or 60)

    return [
        MetricsSnapshot(
            timestamp=h["timestamp"],
            tps=h["tps"],
            rps=h["rps"],
            ttft_mean=h["ttft_mean"],
            ttft_p99=h["ttft_p99"],
            latency_mean=h["latency_mean"],
            latency_p99=h["latency_p99"],
            kv_cache=h["kv_cache"],
            kv_hit_rate=h["kv_hit_rate"],
            running=h["running"],
            waiting=h["waiting"],
            gpu_mem_used=h["gpu_mem_used"],
            gpu_mem_total=h["gpu_mem_total"],
            gpu_util=h["gpu_util"],
            pods=h["pods"],
            pods_ready=h["pods_ready"],
        )
        for h in history_dict
    ]


@router.get("")
@limiter.exempt
async def get_prometheus_metrics() -> PlainTextResponse:
    """
    Expose Prometheus metrics for OpenShift Monitoring.

    Returns plaintext Prometheus format. This endpoint is scraped by ServiceMonitor
    and does not require authentication.
    """
    from fastapi.responses import PlainTextResponse
    from metrics.prometheus_metrics import generate_metrics

    return PlainTextResponse(generate_metrics(), media_type="text/plain; version=0.0.4")
