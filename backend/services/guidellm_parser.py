"""
GuideLLM JSON import parser.

Converts GuideLLM GenerativeBenchmarksReport JSON (version 1) to vllm-optimizer Benchmark models.
- Validates metadata.version == 1
- Converts time units: ms -> seconds (÷1000)
- Maps StatusDistributionSummary percentiles from 'successful' subset
- Sets metadata.source = "guidellm"
"""

import logging
import time

from models.load_test import (
    Benchmark,
    BenchmarkMetadata,
    LatencyStats,
    LoadTestConfig,
    LoadTestResult,
    TpsStats,
)

logger = logging.getLogger(__name__)

SUPPORTED_VERSION = 1


def _extract_latency_stats(dist: dict, ms_to_seconds: bool = False) -> LatencyStats:
    """
    Extract LatencyStats from a GuideLLM StatusDistributionSummary or plain dict.
    Uses 'successful' subset if available, else root-level values.
    Handles both 'median' and 'p50' field names.
    """
    data = dist.get("successful", dist) if isinstance(dist, dict) else {}

    divisor = 1000.0 if ms_to_seconds else 1.0

    def safe_get(key: str, fallback: float = 0.0) -> float:
        val = data.get(key, fallback)
        return float(val) / divisor if val is not None else fallback

    p50 = safe_get("median") or safe_get("p50")

    return LatencyStats(
        mean=safe_get("mean"),
        p50=p50,
        p95=safe_get("p95"),
        p99=safe_get("p99"),
        min=safe_get("min"),
        max=safe_get("max"),
    )


def _extract_tps_stats(dist: dict) -> TpsStats:
    data = dist.get("successful", dist) if isinstance(dist, dict) else {}
    mean = float(data.get("mean", 0.0))
    return TpsStats(
        mean=mean,
        total=mean,  # GuideLLM doesn't have total TPS; use mean as proxy
    )


def parse_guidellm_json(data: dict) -> list[Benchmark]:
    """
    Parse GuideLLM JSON report into a list of Benchmark objects.

    Args:
        data: Parsed JSON dict from GuideLLM output file

    Returns:
        List of Benchmark objects (one per entry in benchmarks[])

    Raises:
        ValueError: If version != 1 or benchmarks array is empty
    """
    metadata = data.get("metadata", {})
    version = metadata.get("version")
    if version != SUPPORTED_VERSION:
        raise ValueError(
            f"Unsupported GuideLLM JSON version: {version}. Only version {SUPPORTED_VERSION} is supported."
        )

    benchmarks_data = data.get("benchmarks", [])
    if not benchmarks_data:
        raise ValueError("No benchmarks found in GuideLLM JSON file.")

    guidellm_version = metadata.get("guidellm_version", "unknown")
    import_timestamp = time.time()

    results = []
    for i, bm in enumerate(benchmarks_data):
        try:
            benchmark = _parse_single_benchmark(bm, i, import_timestamp, guidellm_version)
            results.append(benchmark)
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            logger.warning("Failed to parse benchmark[%d]: %s — skipping", i, e)
            continue

    if not results:
        raise ValueError("No benchmarks could be parsed from the GuideLLM JSON file.")

    return results


def _parse_single_benchmark(bm: dict, index: int, import_timestamp: float, guidellm_version: str) -> Benchmark:
    metrics = bm.get("metrics", {})
    scheduler = bm.get("scheduler_metrics", {})
    bm_config = bm.get("config", {})

    requests_made = scheduler.get("requests_made", {})
    total = int(requests_made.get("total", 0))
    successful = int(requests_made.get("successful", 0))
    failed = int(requests_made.get("errored", 0)) + int(requests_made.get("incomplete", 0))

    measure_start = scheduler.get("measure_start_time", scheduler.get("start_time", 0.0))
    measure_end = scheduler.get("measure_end_time", scheduler.get("end_time", 0.0))
    elapsed = float(measure_end - measure_start) if measure_end > measure_start else 0.0

    # Latency stats — GuideLLM request_latency is already in seconds
    latency_dist = metrics.get("request_latency", {})
    latency = _extract_latency_stats(latency_dist, ms_to_seconds=False)

    # TTFT stats — GuideLLM stores in ms → convert to seconds
    ttft_dist = metrics.get("time_to_first_token_ms", {})
    ttft = _extract_latency_stats(ttft_dist, ms_to_seconds=True)

    # ITL stats — GuideLLM stores in ms → convert to seconds
    itl_dist = metrics.get("inter_token_latency_ms", {})
    itl_data = itl_dist.get("successful", itl_dist) if isinstance(itl_dist, dict) else {}
    itl = None
    if itl_data:
        divisor = 1000.0
        itl = {
            "mean": float(itl_data.get("mean", 0.0)) / divisor,
            "p50": float(itl_data.get("median", itl_data.get("p50", 0.0))) / divisor,
            "p95": float(itl_data.get("p95", 0.0)) / divisor,
            "p99": float(itl_data.get("p99", 0.0)) / divisor,
        }

    tps_dist = metrics.get("tokens_per_second", {})
    tps = _extract_tps_stats(tps_dist)

    rps_actual = float(successful) / elapsed if elapsed > 0 else 0.0

    result = LoadTestResult(
        elapsed=elapsed,
        total=total,
        total_requested=total,
        success=successful,
        failed=failed,
        rps_actual=rps_actual,
        latency=latency,
        ttft=ttft,
        tps=tps,
        backend_cpu_avg=0.0,
        gpu_utilization_avg=None,
        tokens_per_sec=tps.mean,
        metrics_target_matched=False,  # GuideLLM doesn't collect GPU metrics
        itl=itl,
    )

    target_url = bm_config.get("target", "") if isinstance(bm_config, dict) else ""
    model_name = bm_config.get("model", "unknown") if isinstance(bm_config, dict) else "unknown"
    config = LoadTestConfig(
        endpoint=str(target_url),
        model=str(model_name),
        prompt_template="[imported from GuideLLM]",
    )

    bm_metadata = BenchmarkMetadata(
        notes=f"Imported from GuideLLM v{guidellm_version}",
        source="guidellm",
    )

    return Benchmark(
        name=f"guidellm-{index + 1}-{int(import_timestamp)}",
        timestamp=import_timestamp,
        config=config,
        result=result,
        metadata=bm_metadata,
    )
