GAUGE_METRIC_MAP: dict[str, str] = {
    "vllm:kv_cache_usage_perc": "kv_cache_usage_pct",
    "vllm:num_requests_running": "running_requests",
    "vllm:num_requests_waiting": "waiting_requests",
    "kserve_vllm:kv_cache_usage_perc": "kv_cache_usage_pct",
    "kserve_vllm:num_requests_running": "running_requests",
    "kserve_vllm:num_requests_waiting": "waiting_requests",
    "DCGM_FI_DEV_GPU_UTIL": "gpu_utilization_pct",
    "DCGM_FI_DEV_FB_USED": "gpu_memory_used_gb",
}

COUNTER_METRIC_MAP: dict[str, str] = {
    "vllm:generation_tokens_total": "tokens_per_second",
    "vllm:request_success_total": "requests_per_second",
    "vllm:prefix_cache_hits_total": "_prefix_cache_hits",
    "vllm:prefix_cache_queries_total": "_prefix_cache_queries",
    "kserve_vllm:generation_tokens_total": "tokens_per_second",
    "kserve_vllm:request_success_total": "requests_per_second",
    "kserve_vllm:prefix_cache_hits_total": "_prefix_cache_hits",
    "kserve_vllm:prefix_cache_queries_total": "_prefix_cache_queries",
}

HISTOGRAM_METRIC_MAP: dict[str, str] = {
    "vllm:time_to_first_token_seconds": "ttft",
    "vllm:e2e_request_latency_seconds": "latency",
    "kserve_vllm:time_to_first_token_seconds": "ttft",
    "kserve_vllm:e2e_request_latency_seconds": "latency",
}

METRICS_UNIT_SCALE: dict[str, float] = {
    "DCGM_FI_DEV_FB_USED": 1.0 / 1024,
}
