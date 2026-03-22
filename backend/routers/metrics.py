"""
Metrics Router - vLLM Optimizer API

Provides endpoints for retrieving real-time and historical metrics.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from datetime import datetime, timezone
from typing import List, Optional

from models.load_test import MetricsSnapshot, TargetedMetricsResponse
from services.shared import metrics_collector, multi_target_collector

router = APIRouter()


def _convert_to_snapshot(vllm_metrics) -> MetricsSnapshot:
    """Convert VLLMMetrics to MetricsSnapshot
    
    Known limitation: /latest returns 0.0 for idle latency fields;
    /history returns null. This is intentional — /latest shows "last known"
    while /history provides chart-friendly nullable time series.
    """
    if vllm_metrics is None:
        return MetricsSnapshot(
            timestamp=datetime.now(timezone.utc).timestamp(),
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


@router.get("/latest")
async def get_latest_metrics(
    namespace: str | None = None,
    is_name: str | None = None,
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
        registered = await multi_target_collector.register_target(namespace, is_name)
        if not registered:
            raise HTTPException(status_code=409, detail="Max targets reached")

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

    return _convert_to_snapshot(metrics_collector.latest)


@router.get("/history", response_model=List[MetricsSnapshot])
async def get_metrics_history(
    last_n: Optional[int] = 60,
    namespace: str | None = None,
    is_name: str | None = None,
) -> List[MetricsSnapshot]:
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
    
    history_dict = metrics_collector.get_history_dict(last_n or 60)
    
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
async def get_prometheus_metrics() -> PlainTextResponse:
    """
    Expose Prometheus metrics for OpenShift Monitoring.

    Returns plaintext Prometheus format. This endpoint is scraped by ServiceMonitor
    and does not require authentication.
    """
    from metrics.prometheus_metrics import generate_metrics
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(generate_metrics(), media_type="text/plain; version=0.0.4")






