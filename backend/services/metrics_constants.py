_PREFIX_ALIASES: tuple[str, ...] = ("kserve_vllm:",)


def normalize_metric_name(name: str) -> str:
    for alias in _PREFIX_ALIASES:
        if name.startswith(alias):
            return "vllm:" + name[len(alias) :]
    return name


GAUGE_METRIC_MAP: dict[str, str] = {
    "vllm:kv_cache_usage_perc": "kv_cache_usage_pct",
    "vllm:num_requests_running": "running_requests",
    "vllm:num_requests_waiting": "waiting_requests",
    "vllm:num_requests_swapped": "swapped_requests",
    "DCGM_FI_DEV_GPU_UTIL": "gpu_utilization_pct",
    "DCGM_FI_DEV_FB_USED": "gpu_memory_used_gb",
    "DCGM_FI_DEV_FB_FREE": "gpu_memory_free_gb",
    "DCGM_FI_DEV_FB_RESERVED": "gpu_memory_reserved_gb",
}

COUNTER_METRIC_MAP: dict[str, str] = {
    "vllm:generation_tokens_total": "tokens_per_second",
    "vllm:request_success_total": "requests_per_second",
    "vllm:prefix_cache_hits_total": "_prefix_cache_hits",
    "vllm:prefix_cache_queries_total": "_prefix_cache_queries",
}

HISTOGRAM_METRIC_MAP: dict[str, str] = {
    "vllm:time_to_first_token_seconds": "ttft",
    "vllm:e2e_request_latency_seconds": "latency",
    "vllm:time_per_output_token_seconds": "tpot",
    "vllm:request_queue_time_seconds": "queue_time",
}

METRICS_UNIT_SCALE: dict[str, float] = {
    "DCGM_FI_DEV_FB_USED": 1.0 / 1024,
    "DCGM_FI_DEV_FB_FREE": 1.0 / 1024,
    "DCGM_FI_DEV_FB_RESERVED": 1.0 / 1024,
}
