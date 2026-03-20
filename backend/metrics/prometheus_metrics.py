"""
Prometheus metrics definitions for vLLM Optimizer backend.
Exposes metrics in Prometheus format for OpenShift Monitoring.
"""

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST
)

# Use a custom registry to avoid duplicate registration issues
# This ensures metrics are only registered once even if module is imported multiple times
_registry = CollectorRegistry()

# ── Metric Definitions ───────────────────────────────────────────────────────

# Gauges (current rate values)
request_rate_metric = Gauge(
    'vllm_optimizer_requests_per_second',
    'Current request throughput in requests per second',
    ['model'],
    registry=_registry
)

token_rate_metric = Gauge(
    'vllm_optimizer_tokens_per_second',
    'Current token generation rate in tokens per second',
    ['model'],
    registry=_registry
)

# Gauges (point-in-time)
num_requests_running_metric = Gauge(
    'vllm_optimizer_num_requests_running',
    'Number of currently running vLLM requests (mirrored by optimizer)',
    registry=_registry
)

num_requests_waiting_metric = Gauge(
    'vllm_optimizer_num_requests_waiting',
    'Number of requests waiting in queue (mirrored by optimizer)',
    registry=_registry
)

gpu_cache_usage_perc_metric = Gauge(
    'vllm_optimizer_gpu_cache_usage_perc',
    'GPU KV cache usage percentage (mirrored by optimizer)',
    registry=_registry
)

gpu_utilization_metric = Gauge(
    'vllm_optimizer_gpu_utilization',
    'GPU utilization percentage (mirrored by optimizer)',
    registry=_registry
)

time_to_first_token_seconds_metric = Histogram(
    'vllm_optimizer_time_to_first_token_seconds',
    'Time to first token distribution (mirrored by optimizer)',
    ['model'],
    registry=_registry
)

e2e_request_latency_seconds_metric = Histogram(
    'vllm_optimizer_e2e_request_latency_seconds',
    'End-to-end request latency distribution (mirrored by optimizer)',
    ['model'],
    registry=_registry
)

metrics_collection_duration_metric = Histogram(
    'vllm_optimizer:metrics_collection_duration_seconds',
    'Time spent collecting metrics from Prometheus/K8s',
    registry=_registry
)

tuner_trials_total = Counter(
    'vllm_optimizer_tuner_trials_total',
    'Total number of auto-tuning trials by status',
    ['status'],
    registry=_registry
)

tuner_best_score = Gauge(
    'vllm_optimizer_tuner_best_score',
    'Best optimization score achieved by the auto-tuner',
    ['objective'],
    registry=_registry
)

tuner_trial_duration_seconds = Histogram(
    'vllm_optimizer_tuner_trial_duration_seconds',
    'Duration of each auto-tuning trial in seconds',
    buckets=[10, 30, 60, 120, 300, 600],
    registry=_registry
)

 


def update_metrics(data):
    """
    Update Prometheus metrics with latest VLLMMetrics data.
    
    Args:
        data: VLLMMetrics object containing current metrics
    """
    # Gauges - set directly
    num_requests_running_metric.set(data.running_requests)
    num_requests_waiting_metric.set(data.waiting_requests)
    gpu_cache_usage_perc_metric.set(data.kv_cache_usage_pct)
    gpu_utilization_metric.set(data.gpu_utilization_pct)
    
    # Gauges - set current rate values directly
    request_rate_metric.labels(model='default').set(data.requests_per_second)
    token_rate_metric.labels(model='default').set(data.tokens_per_second)
    
    # Histograms - observe latency values (convert ms to seconds)
    time_to_first_token_seconds_metric.labels(model='default').observe(data.mean_ttft_ms / 1000.0)
    e2e_request_latency_seconds_metric.labels(model='default').observe(data.mean_e2e_latency_ms / 1000.0)


def generate_metrics():
    """
    Generate Prometheus-formatted metrics output.
    
    Returns:
        bytes: Metrics in Prometheus text format
    """
    return generate_latest(_registry)
