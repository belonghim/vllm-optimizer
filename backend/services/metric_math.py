"""Pure metric math helpers extracted from MultiTargetMetricsCollector.

These functions are stateless computations over raw Prometheus scrape data.
The collector's methods delegate here; tests call the methods, not these functions.
"""

import math

from services.multi_target_collector import TargetCache


def _compute_rates(
    pod_ip: str,
    target: TargetCache,
    raw_counters: dict[str, float],
    now: float,
) -> dict[str, float]:
    rates: dict[str, float] = {}
    if pod_ip not in target.prev_counters:
        target.prev_counters[pod_ip] = {}
    prev = target.prev_counters[pod_ip]
    for metric_name, current_value in raw_counters.items():
        ts_key = metric_name + "_ts"
        if metric_name not in prev:
            prev[metric_name] = current_value
            prev[ts_key] = now
            rates[metric_name] = 0.0
        else:
            prev_val = prev[metric_name]
            prev_ts = prev[ts_key]
            elapsed = now - prev_ts
            if elapsed <= 0:
                rates[metric_name] = 0.0
                continue
            delta = current_value - prev_val
            if delta < 0:
                prev[metric_name] = current_value
                prev[ts_key] = now
                rates[metric_name] = 0.0
                continue
            prev[metric_name] = current_value
            prev[ts_key] = now
            rates[metric_name] = delta / elapsed
    return rates


def _compute_histogram_stats(raw_histograms: dict[str, float]) -> dict[str, float]:
    ttft_sum = raw_histograms.get("ttft_sum", 0.0)
    ttft_count = raw_histograms.get("ttft_count", 0.0)
    latency_sum = raw_histograms.get("latency_sum", 0.0)
    latency_count = raw_histograms.get("latency_count", 0.0)
    tpot_sum = raw_histograms.get("tpot_sum", 0.0)
    tpot_count = raw_histograms.get("tpot_count", 0.0)
    queue_time_sum = raw_histograms.get("queue_time_sum", 0.0)
    queue_time_count = raw_histograms.get("queue_time_count", 0.0)
    mean_ttft_ms = (ttft_sum / ttft_count) * 1000 if ttft_count > 0 else 0.0
    mean_e2e_latency_ms = (latency_sum / latency_count) * 1000 if latency_count > 0 else 0.0
    mean_tpot_ms = (tpot_sum / tpot_count) * 1000 if tpot_count > 0 else 0.0
    mean_queue_time_ms = (queue_time_sum / queue_time_count) * 1000 if queue_time_count > 0 else 0.0
    return {
        "mean_ttft_ms": mean_ttft_ms,
        "mean_e2e_latency_ms": mean_e2e_latency_ms,
        "mean_tpot_ms": mean_tpot_ms,
        "mean_queue_time_ms": mean_queue_time_ms,
    }


def _compute_histogram_quantile(
    buckets: list[tuple[float, float]],
    quantile: float,
    scale: float = 1.0,
    *,
    from_rates: bool = True,
) -> float:
    """Compute histogram quantile from buckets.

    Args:
        buckets: List of (le, count) tuples where le is the upper bound of the bucket.
        quantile: Quantile to compute (0-1).
        scale: Multiplier for le values. Default 1.0. Set to 1000.0 for seconds->ms conversion.
        from_rates: If True, buckets contain rate values (from rate computation). If False, buckets contain
            cumulative counts (direct from first scrape). Default True.
    """
    if not buckets or quantile < 0 or quantile > 1:
        return 0.0

    sorted_buckets = sorted(buckets, key=lambda item: item[0])
    total_count = 0.0
    for le, count in sorted_buckets:
        if math.isnan(count) or count < 0:
            continue
        if math.isinf(le):
            total_count = max(total_count, count)
            break
        total_count = max(total_count, count)
    if total_count <= 0:
        return 0.0

    rank = quantile * total_count
    lower_bound = 0.0
    lower_count = 0.0

    for upper_bound, upper_count in sorted_buckets:
        if math.isnan(upper_count) or upper_count < 0:
            continue
        if upper_count >= rank:
            if upper_count == lower_count:
                return lower_bound * scale
            if math.isinf(upper_bound):
                return lower_bound * scale
            interpolated = lower_bound + (
                (upper_bound - lower_bound) * (rank - lower_count) / (upper_count - lower_count)
            )
            return interpolated * scale

        if not math.isinf(upper_bound):
            lower_bound = upper_bound
        lower_count = upper_count

    return 0.0


def _compute_histogram_rates(
    pod_ip: str,
    target: TargetCache,
    current_buckets: dict[str, dict[float, float]],
    now: float,
) -> dict[str, list[tuple[float, float]]]:
    if pod_ip not in target.prev_hist_buckets:
        target.prev_hist_buckets[pod_ip] = {}
        target.prev_hist_timestamps[pod_ip] = now

    prev_buckets = target.prev_hist_buckets[pod_ip]
    prev_ts = target.prev_hist_timestamps.get(pod_ip, now)
    elapsed = now - prev_ts

    result: dict[str, list[tuple[float, float]]] = {}

    for hist_name, current_hist in current_buckets.items():
        prev_hist = prev_buckets.get(hist_name, {})

        if not prev_hist:
            result[hist_name] = [(le, 0.0) for le in current_hist]
            continue

        delta_buckets: dict[float, float] = {}
        for le, current_count in current_hist.items():
            prev_count = prev_hist.get(le, 0.0)
            delta = current_count - prev_count
            if delta < 0:
                delta = 0.0
            delta_buckets[le] = delta

        if elapsed > 0:
            rate_buckets = [(le, delta / elapsed) for le, delta in delta_buckets.items()]
        else:
            rate_buckets = [(le, 0.0) for le in delta_buckets]

        result[hist_name] = sorted(rate_buckets, key=lambda x: x[0])

    target.prev_hist_buckets[pod_ip] = current_buckets
    target.prev_hist_timestamps[pod_ip] = now

    return result
