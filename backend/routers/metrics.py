from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from services.rate_limiter import limiter
from models.load_test import (
    BatchMetricsRequest,
    BatchMetricsResponse,
    ErrorResponse,
    MetricsSnapshot,
    TargetedMetricsResponse,
)
from services.shared import multi_target_collector as _default_collector, runtime_config as _default_runtime_config
from services.metrics_service import (
    _convert_to_snapshot,
    _fetch_query_range,
    _get_history_from_thanos,
    _TIME_RANGE_CONFIG,
    MAX_HISTORY_POINTS,
)

router = APIRouter()


def get_multi_target_collector():
    return _default_collector


def get_runtime_config():
    return _default_runtime_config


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
            )
        return TargetedMetricsResponse(
            status="ready",
            data=_convert_to_snapshot(vllm_metrics),
            hasMonitoringLabel=has_monitoring_label,
        )

    default_namespace = rt_config.vllm_namespace
    default_is_name = rt_config.vllm_is_name
    _ = await collector.register_target(default_namespace, default_is_name)
    vllm_metrics = await collector.get_metrics(default_namespace, default_is_name)
    return _convert_to_snapshot(vllm_metrics)


@router.post("/batch")
@limiter.limit("120/minute")
async def get_batch_metrics(
    request: Request,
    body: BatchMetricsRequest,
    collector=Depends(get_multi_target_collector),
) -> BatchMetricsResponse:
    results: dict[str, dict[str, object]] = {}

    for target in body.targets:
        key = f"{target.namespace}/{target.inferenceService}"
        registered = await collector.register_target(target.namespace, target.inferenceService, cr_type=target.cr_type)
        if not registered:
            results[key] = {"data": None, "status": "max_targets_reached"}
            continue

        vllm_metrics = await collector.get_metrics(target.namespace, target.inferenceService)
        has_monitoring_label = collector.get_has_monitoring_label(target.namespace, target.inferenceService)

        if body.time_range in _TIME_RANGE_CONFIG:
            history = await _get_history_from_thanos(
                target.namespace, target.inferenceService, target.cr_type, body.time_range, collector
            )
        else:
            target_cache = collector._targets.get(key)
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
    last_n: int | None = Query(default=60, ge=1, le=10000),
    namespace: str | None = None,
    is_name: str | None = None,
    collector=Depends(get_multi_target_collector),
) -> list[MetricsSnapshot]:
    if namespace is not None and is_name is not None:
        target = collector._targets.get(f"{namespace}/{is_name}")
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


@router.get("")
@limiter.exempt
async def get_prometheus_metrics() -> PlainTextResponse:
    from fastapi.responses import PlainTextResponse
    from metrics.prometheus_metrics import generate_metrics

    return PlainTextResponse(generate_metrics(), media_type="text/plain; version=0.0.4")
