import asyncio
import math
import os
import time as time_mod
from datetime import UTC, datetime

import httpx
from models.load_test import MetricsSnapshot
from services.retry_helper import with_retry

MAX_HISTORY_POINTS = 1000

PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091",
)

_TIME_RANGE_CONFIG: dict[str, dict[str, int]] = {
    "1h": {"duration": 3600, "step": 10},
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


async def _fetch_query_range_multi_result(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    query: str,
    start: float,
    end: float,
    step: int,
) -> dict[str, list[tuple[float, float]]]:
    """
    Fetch multiple results from Prometheus query_range, returning a dict mapping pod names to time series.

    Unlike _fetch_query_range() which handles aggregated queries (single result),
    this method parses ALL results from the Prometheus response, extracting the 'pod' label
    from each result to create a pod->time_series mapping.

    Returns:
        Dict mapping pod names to lists of (timestamp, value) tuples.
        If 'pod' label is missing, uses "pod_0", "pod_1", etc. as fallback keys.
    """
    try:

        async def _do_get():
            r = await client.get(
                f"{PROMETHEUS_URL}/api/v1/query_range",
                params={"query": query, "start": start, "end": end, "step": step},
                headers=headers,
            )
            r.raise_for_status()
            return r

        response = await with_retry(_do_get, label="thanos-query-range-multi")
        data = response.json()
        if data.get("status") != "success":
            return {}
        results = data.get("data", {}).get("result", [])
        if not results:
            return {}

        result: dict[str, list[tuple[float, float]]] = {}
        for i, item in enumerate(results):
            metric = item.get("metric", {})
            pod_name = metric.get("pod", f"pod_{i}")
            values = item.get("values", [])
            parsed: list[tuple[float, float]] = []
            for item_val in values:
                try:
                    ts = float(item_val[0])
                    v = float(item_val[1])
                    if not (math.isnan(v) or math.isinf(v)):
                        parsed.append((ts, v))
                except (ValueError, IndexError):
                    pass
            if parsed:
                result[pod_name] = parsed
        return result
    except (httpx.HTTPError, ValueError, KeyError):
        return {}


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


def _build_per_pod_snapshots_from_ts_data(
    pod_metric_series: dict[str, dict[str, list[tuple[float, float]]]],
) -> list[dict]:
    """
    Build snapshots from per-pod metric series.

    Args:
        pod_metric_series: Dict mapping pod_name -> {metric_field: [(ts, val), ...]}

    Returns:
        List of snapshots, each containing per-pod metrics with pod_name field.
    """
    if not pod_metric_series:
        return []

    all_timestamps: set[float] = set()
    for pod_series in pod_metric_series.values():
        for series in pod_series.values():
            for ts, _ in series:
                all_timestamps.add(ts)

    if not all_timestamps:
        return []

    pod_names = sorted(pod_metric_series.keys())
    all_fields = set()
    for pod_series in pod_metric_series.values():
        all_fields.update(pod_series.keys())

    ts_data: dict[float, dict[str, dict[str, float]]] = {ts: {pod: {} for pod in pod_names} for ts in all_timestamps}

    for pod_name, pod_series in pod_metric_series.items():
        for metric_field, series in pod_series.items():
            snapshot_field = _METRIC_FIELD_MAP.get(metric_field)
            if not snapshot_field:
                continue
            for ts, value in series:
                ts_data[ts][pod_name][snapshot_field] = value

    snapshots = []
    for ts in sorted(all_timestamps):
        for pod_name in pod_names:
            pod_data = ts_data[ts][pod_name]
            snap = MetricsSnapshot(
                timestamp=ts,
                tps=pod_data.get("tps", 0.0),
                rps=pod_data.get("rps", 0.0),
                ttft_mean=pod_data.get("ttft_mean", 0.0),
                ttft_p99=pod_data.get("ttft_p99", 0.0),
                latency_mean=pod_data.get("latency_mean", 0.0),
                latency_p99=pod_data.get("latency_p99", 0.0),
                kv_cache=pod_data.get("kv_cache", 0.0),
                kv_hit_rate=pod_data.get("kv_hit_rate", 0.0),
                running=int(pod_data.get("running", 0)),
                waiting=int(pod_data.get("waiting", 0)),
                gpu_mem_used=pod_data.get("gpu_mem_used", 0.0),
                gpu_mem_total=pod_data.get("gpu_mem_total", 0.0),
                gpu_util=pod_data.get("gpu_util", 0.0),
                pods=0,
                pods_ready=0,
            )
            snap_dict = snap.model_dump()
            snap_dict["pod_name"] = pod_name
            snapshots.append(snap_dict)

    return snapshots


async def _get_history_from_thanos(
    namespace: str,
    is_name: str,
    cr_type: str | None,
    time_range: str,
    collector,
    per_pod: bool = False,
) -> list[dict]:
    cfg = _TIME_RANGE_CONFIG.get(time_range)
    if not cfg:
        return []

    now = time_mod.time()
    start = now - cfg["duration"]
    step = cfg["step"]

    queries = (
        collector._build_pod_queries(namespace, is_name, cr_type)
        if per_pod
        else collector._build_target_queries(namespace, is_name, cr_type)
    )
    headers: dict[str, str] = {}
    token = collector._token
    if token:
        headers["Authorization"] = f"Bearer {token}"

    field_names = list(queries.keys())
    async with httpx.AsyncClient(verify=False, timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        if per_pod:
            pod_series_list = await asyncio.gather(
                *[_fetch_query_range_multi_result(client, headers, queries[f], start, now, step) for f in field_names]
            )
            pod_metric_series: dict[str, dict[str, list[tuple[float, float]]]] = {}
            for i, pod_series in enumerate(pod_series_list):
                metric_field = field_names[i]
                for pod_name, series in pod_series.items():
                    if pod_name not in pod_metric_series:
                        pod_metric_series[pod_name] = {}
                    pod_metric_series[pod_name][metric_field] = series
            return _build_per_pod_snapshots_from_ts_data(pod_metric_series)
        else:
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
