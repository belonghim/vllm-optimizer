import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from models.load_test import (
    BatchMetricsRequest,
    BatchMetricsResponse,
    ErrorResponse,
    MetricsSnapshot,
    PerPodMetricSnapshot,
    PerPodMetricsResponse,
    TargetedMetricsResponse,
)
from services.cr_adapter import get_cr_adapter
from services.metrics_service import (
    _TIME_RANGE_CONFIG,
    MAX_HISTORY_POINTS,
    _convert_to_snapshot,
    _get_history_from_thanos,
)
from services.rate_limiter import limiter
from services.shared import multi_target_collector as _default_collector
from services.shared import runtime_config as _default_runtime_config

router = APIRouter()


def get_multi_target_collector():
    return _default_collector


def get_runtime_config():
    return _default_runtime_config


@router.get(
    "/latest",
    response_model=None,
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
    collector=Depends(get_multi_target_collector),
    rt_config=Depends(get_runtime_config),
) -> MetricsSnapshot | TargetedMetricsResponse:
    if namespace is not None and is_name is not None:
        registered = await collector.register_target(namespace, is_name, cr_type=cr_type or rt_config.cr_type)
        if not registered:
            raise HTTPException(
                status_code=409,
                detail=ErrorResponse(
                    error="Max targets reached",
                    error_type="max_targets",
                ).model_dump(),
            )

        vllm_metrics = await collector.get_metrics(namespace, is_name)
        has_monitoring_label = collector.get_has_monitoring_label(namespace, is_name)

        if vllm_metrics is None:
            return TargetedMetricsResponse(
                status="collecting",
                data=None,
                hasMonitoringLabel=has_monitoring_label,
                crExists=collector.get_cr_exists(namespace, is_name),
            )
        return TargetedMetricsResponse(
            status="ready",
            data=_convert_to_snapshot(vllm_metrics),
            hasMonitoringLabel=has_monitoring_label,
            crExists=collector.get_cr_exists(namespace, is_name),
        )

    default_namespace = rt_config.vllm_namespace
    default_is_name = rt_config.vllm_is_name
    _ = await collector.register_target(default_namespace, default_is_name)
    vllm_metrics = await collector.get_metrics(default_namespace, default_is_name)
    return _convert_to_snapshot(vllm_metrics)


@router.post("/batch", response_model=BatchMetricsResponse)
@limiter.limit("120/minute")
async def get_batch_metrics(
    request: Request,
    body: BatchMetricsRequest,
    collector=Depends(get_multi_target_collector),
) -> BatchMetricsResponse:
    results: dict[str, dict[str, object]] = {}

    for target in body.targets:
        cr_type = target.cr_type or "inferenceservice"
        key = f"{target.namespace}/{target.inferenceService}/{cr_type}"
        registered = await collector.register_target(target.namespace, target.inferenceService, cr_type=target.cr_type)
        if not registered:
            results[key] = {"data": None, "status": "max_targets_reached"}
            continue

        vllm_metrics = await collector.get_metrics(target.namespace, target.inferenceService, cr_type=target.cr_type)
        has_monitoring_label = collector.get_has_monitoring_label(
            target.namespace, target.inferenceService, cr_type=target.cr_type
        )

        if body.time_range in _TIME_RANGE_CONFIG:
            history = await _get_history_from_thanos(
                target.namespace, target.inferenceService, target.cr_type, body.time_range, collector
            )
        else:
            target_cache = collector.get_target(target.namespace, target.inferenceService, cr_type=target.cr_type)
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
                "crExists": collector.get_cr_exists(
                    target.namespace,
                    target.inferenceService,
                    cr_type=target.cr_type,
                ),
            }
        else:
            snapshot = _convert_to_snapshot(vllm_metrics)
            results[key] = {
                "data": snapshot.model_dump(),
                "status": "ready",
                "hasMonitoringLabel": has_monitoring_label,
                "history": history,
                "crExists": collector.get_cr_exists(
                    target.namespace,
                    target.inferenceService,
                    cr_type=target.cr_type,
                ),
            }

    return BatchMetricsResponse(results=results)


@router.post("/pods", response_model=None)
@limiter.limit("120/minute")
async def get_pod_metrics(
    request: Request,
    body: BatchMetricsRequest,
    collector=Depends(get_multi_target_collector),
) -> dict[str, PerPodMetricsResponse]:
    """Get per-pod metrics for multiple targets.

    Returns a ``dict[str, PerPodMetricsResponse]`` keyed by
    ``"{namespace}/{inferenceService}/{cr_type}"``, e.g.
    ``"vllm-lab-dev/llm-ov/inferenceservice"``.

    Why ``response_model=None`` (Case B):
        FastAPI / OpenAPI cannot express a dynamic-key dict schema
        (``dict[str, PerPodMetricsResponse]``) in its type system. Setting
        ``response_model=None`` disables automatic schema generation for this
        endpoint.

    Frontend note:
        ``MultiTargetSelector.tsx`` accesses ``data[key]?.per_pod`` directly on
        the response root. Wrapping the response in a ``results`` dict would be a
        breaking change for the frontend, so the raw ``dict`` is returned as-is.
    """
    import time

    from models.load_test import MetricsSnapshot

    results: dict[str, PerPodMetricsResponse] = {}

    for target in body.targets:
        cr_type = target.cr_type or "inferenceservice"
        key = f"{target.namespace}/{target.inferenceService}/{cr_type}"
        registered = await collector.register_target(target.namespace, target.inferenceService, cr_type=target.cr_type)
        if not registered:
            results[key] = PerPodMetricsResponse(
                aggregated=MetricsSnapshot(timestamp=time.time()),
                per_pod=[],
                pod_names=[],
                timestamp=time.time(),
            )
            continue

        # Get aggregated metrics (same as /batch)
        vllm_metrics = await collector.get_metrics(target.namespace, target.inferenceService)
        snapshot = _convert_to_snapshot(vllm_metrics)

        # Build per-pod queries and fetch results
        queries = collector._build_pod_queries(target.namespace, target.inferenceService, target.cr_type)
        headers: dict[str, str] = {}
        if collector._token:
            headers["Authorization"] = f"Bearer {collector._token}"

        cr_type = target.cr_type or "inferenceservice"
        adapter = get_cr_adapter(cr_type)
        pod_name_pattern = adapter.dcgm_pod_pattern(target.inferenceService)

        # Fetch all pod queries in parallel
        fetch_tasks = [
            collector._fetch_prometheus_multi_result(headers, query, pod_name_pattern) for query in queries.values()
        ]
        query_results = await asyncio.gather(*fetch_tasks)

        # Build pod_name -> metrics mapping from all query results
        # query_results[i] corresponds to queries[keys[i]]
        metric_names = list(queries.keys())
        pod_metrics: dict[str, dict[str, float | int | None]] = {}
        for metric_name, pod_result in zip(metric_names, query_results, strict=False):
            for pod_name, value in pod_result.items():
                if pod_name not in pod_metrics:
                    pod_metrics[pod_name] = {
                        "tps": None,
                        "rps": None,
                        "kv_cache": None,
                        "running": None,
                        "waiting": None,
                        "gpu_util": None,
                        "gpu_mem_used": None,
                    }
                # Map metric name to PerPodMetricSnapshot field
                snapshot_field = _pod_metric_to_snapshot_field(metric_name)
                if snapshot_field and value is not None:
                    pod_metrics[pod_name][snapshot_field] = value

        # Convert to PerPodMetricSnapshot list
        pod_names = sorted(pod_metrics.keys())
        per_pod_snapshots = [
            PerPodMetricSnapshot(
                pod_name=pod_name,
                tps=pod_metrics[pod_name].get("tps"),
                rps=pod_metrics[pod_name].get("rps"),
                kv_cache=pod_metrics[pod_name].get("kv_cache"),
                running=pod_metrics[pod_name].get("running"),
                waiting=pod_metrics[pod_name].get("waiting"),
                gpu_util=pod_metrics[pod_name].get("gpu_util"),
                gpu_mem_used=pod_metrics[pod_name].get("gpu_mem_used"),
            )
            for pod_name in pod_names
        ]

        results[key] = PerPodMetricsResponse(
            aggregated=snapshot,
            per_pod=per_pod_snapshots,
            pod_names=pod_names,
            timestamp=time.time(),
        )

    return results


@router.post("/pods/history", response_model=BatchMetricsResponse)
@limiter.limit("120/minute")
async def get_pods_history(
    request: Request,
    body: BatchMetricsRequest,
    collector=Depends(get_multi_target_collector),
) -> BatchMetricsResponse:
    """Get per-pod history for multiple targets via Thanos.

    Returns per-pod time series metrics for each target using
    _get_history_from_thanos with per_pod=True.
    """
    results: dict[str, dict[str, object]] = {}

    for target in body.targets:
        cr_type = target.cr_type or "inferenceservice"
        key = f"{target.namespace}/{target.inferenceService}/{cr_type}"
        registered = await collector.register_target(target.namespace, target.inferenceService, cr_type=target.cr_type)
        if not registered:
            results[key] = {"data": None, "status": "max_targets_reached", "history": []}
            continue

        if body.time_range in _TIME_RANGE_CONFIG:
            history = await _get_history_from_thanos(
                target.namespace, target.inferenceService, target.cr_type, body.time_range, collector, per_pod=True
            )
        else:
            history = []

        results[key] = {
            "data": None,
            "status": "ready",
            "history": history,
        }

    return BatchMetricsResponse(results=results)


def _pod_metric_to_snapshot_field(metric_name: str) -> str | None:
    """Map query metric name to PerPodMetricSnapshot field name."""
    mapping = {
        "tokens_per_second": "tps",
        "requests_per_second": "rps",
        "kv_cache_usage_pct": "kv_cache",
        "running_requests": "running",
        "waiting_requests": "waiting",
        "gpu_utilization_pct": "gpu_util",
        "gpu_memory_used_gb": "gpu_mem_used",
    }
    return mapping.get(metric_name)


@router.get("/history", response_model=list[MetricsSnapshot])
@limiter.limit("120/minute")
async def get_metrics_history(
    request: Request,
    last_n: int | None = Query(default=60, ge=1, le=10000),
    namespace: str | None = None,
    is_name: str | None = None,
    collector=Depends(get_multi_target_collector),
) -> list[MetricsSnapshot]:
    if namespace is not None and is_name is not None:
        target = collector.get_target(namespace, is_name)
        if target is None:
            return []
        n = last_n if last_n is not None else 60
        history = list(target.history)[-n:]
        return [_convert_to_snapshot(m) for m in history]

    history_dict = collector.get_history_dict(last_n or 60)

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


@router.get("", response_model=None)
@limiter.exempt
async def get_prometheus_metrics() -> PlainTextResponse:
    from fastapi.responses import PlainTextResponse
    from metrics.prometheus_metrics import generate_metrics

    return PlainTextResponse(generate_metrics(), media_type="text/plain; version=0.0.4")
