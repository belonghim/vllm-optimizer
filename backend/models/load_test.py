"""
Pydantic models for vLLM Optimizer API

This module defines all data models used for API request/response validation
and internal data structures. Models are divided into:
- Load test configuration and results
- Performance statistics
- Auto-tuning configuration and trial results
"""
from pydantic import BaseModel, Field
from typing import Any, Optional


class LoadTestConfig(BaseModel):
    """Load test configuration"""
    endpoint: str = Field(default="", description="vLLM endpoint URL (empty = use server default from VLLM_ENDPOINT env)")
    model: str = Field(default="auto", description="Model name")
    prompt_template: str = Field(default="Hello, how are you?", description="Prompt for generation")
    total_requests: int = Field(default=100, ge=1, description="Total number of requests")
    concurrency: int = Field(default=10, ge=1, description="Concurrent requests")
    rps: int = Field(default=0, ge=0, description="Requests per second (0=unlimited)")
    max_tokens: int = Field(default=256, ge=1, description="Max tokens to generate")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Temperature for generation")
    stream: bool = Field(default=True, description="Enable streaming mode")


class RequestResult(BaseModel):
    """Single request result"""
    req_id: int
    success: bool
    latency: float = Field(description="Total latency in seconds")
    ttft: float | None = Field(default=None, description="Time to first token in seconds")
    output_tokens: int = Field(default=0, description="Number of output tokens")
    tps: float = Field(default=0.0, description="Tokens per second")
    error: str | None = Field(default=None, description="Error message if failed")


class LatencyStats(BaseModel):
    """Latency statistics"""
    mean: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    min: float = 0.0
    max: float = 0.0


class TpsStats(BaseModel):
    """Tokens per second statistics"""
    mean: float = 0.0
    total: float = 0.0


class LoadTestResult(BaseModel):
    """Aggregated load test result"""
    elapsed: float = 0.0
    total: int = 0
    total_requested: int = 0
    success: int = 0
    failed: int = 0
    rps_actual: float = 0.0
    latency: LatencyStats = Field(default_factory=LatencyStats)
    ttft: LatencyStats = Field(default_factory=LatencyStats)
    tps: TpsStats = Field(default_factory=TpsStats)
    # Performance sampling fields — populated during load test
    backend_cpu_avg: float = 0.0
    gpu_utilization_avg: float = 0.0
    tokens_per_sec: float = 0.0
    metrics_target_matched: bool = Field(default=True, description="GPU 메트릭 수집 대상이 부하 테스트 대상과 일치하는지 여부 (불일치 시 GPU Eff. 계산값이 무의미)")










class TuningConfig(BaseModel):
    """Configuration for auto-tuning parameters"""
    # Search space ranges
    max_num_seqs_range: tuple[int, int] = Field(default=(64, 512), description="Range for max-num-seqs parameter")
    gpu_memory_utilization_range: tuple[float, float] = Field(default=(0.80, 0.95), description="Range for GPU memory utilization")
    max_model_len_range: tuple[int, int] = Field(default=(2048, 8192), description="Range for max-model-len parameter")
    # Expanded search space and tuning controls
    max_num_batched_tokens_range: tuple[int, int] = Field(default=(256, 2048), description="Range for max-num-batched-tokens parameter")
    block_size_options: list[int] = Field(default=[8, 16, 32], description="KV cache block size options")
    include_swap_space: bool = Field(default=False, description="Enable swap_space parameter search (disable on CPU/OpenVINO)")
    swap_space_range: tuple[float, float] = Field(default=(1.0, 8.0), description="Range for swap-space parameter (GB)")
    eval_concurrency: int = Field(default=16, ge=1, description="Concurrent requests during evaluation load test")
    eval_rps: int = Field(default=20, ge=0, description="Requests per second during evaluation (0=unlimited)")
    eval_fast_fraction: float = Field(default=0.5, ge=0.1, le=1.0, description="Fraction of eval_requests for MedianPruner fast probe")
    # Optimization objectives
    objective: str = Field(default="tps", description="Optimization objective: tps, latency, or balanced")
    n_trials: int = Field(default=10, ge=1, description="Number of optimization trials")
    warmup_requests: int = Field(default=20, ge=0, description="Number of warmup requests per trial")
    eval_requests: int = Field(default=100, ge=1, description="Number of evaluation requests per trial")



class TuningTrial(BaseModel):
    """Individual tuning trial result"""
    trial_id: int = Field(description="Trial number")
    params: dict[str, Any] = Field(default_factory=dict, description="Trial parameters")
    tps: float = Field(description="Tokens per second achieved")
    p99_latency: float = Field(description="P99 latency in seconds")
    score: float = Field(description="Optimization score")
    status: str = Field(default="pending", description="Trial status: pending, completed, failed")
    is_pareto_optimal: bool = Field(default=False, description="Whether this trial is on the Pareto front")
    pruned: bool = Field(default=False, description="Whether this trial was pruned by MedianPruner")


class MetricsSnapshot(BaseModel):
    """Real-time vLLM performance metrics snapshot"""
    timestamp: float = Field(description="Unix timestamp of the snapshot")
    tps: float = Field(default=0.0, description="Tokens per second")
    rps: float = Field(default=0.0, description="Requests per second")
    ttft_mean: Optional[float] = Field(default=None, description="Time to first token (mean) in ms")
    ttft_p99: Optional[float] = Field(default=None, description="Time to first token (P99) in ms")
    latency_mean: Optional[float] = Field(default=None, description="End-to-end latency (mean) in ms")
    latency_p99: Optional[float] = Field(default=None, description="End-to-end latency (P99) in ms")
    kv_cache: float = Field(default=0.0, description="KV cache usage percentage")
    kv_hit_rate: float = Field(default=0.0, description="KV cache hit rate")
    running: int = Field(default=0, description="Number of currently running requests")
    waiting: int = Field(default=0, description="Number of requests waiting in queue")
    gpu_mem_used: float = Field(default=0.0, description="GPU memory used in GB")
    gpu_mem_total: float = Field(default=0.0, description="Total GPU memory in GB")
    gpu_util: float = Field(default=0.0, description="GPU utilization percentage")
    pods: int = Field(default=0, description="Total number of vLLM pods")
    pods_ready: int = Field(default=0, description="Number of ready vLLM pods")


class Benchmark(BaseModel):
    """Saved benchmark result for comparison"""
    id: int | None = Field(default=None, description="Unique benchmark identifier")
    name: str = Field(description="User-provided benchmark name")
    timestamp: float | None = Field(default=None, description="Unix timestamp when benchmark was saved")
    config: LoadTestConfig = Field(description="Load test configuration used")
    result: LoadTestResult = Field(description="Final load test results")


class TargetedMetricsResponse(BaseModel):
    """Response for targeted metrics queries via namespace + is_name."""
    status: str = Field(description='"collecting" if metrics not yet available, "ready" if data present')
    data: MetricsSnapshot | None = Field(default=None, description="Latest metrics snapshot, null when status is collecting")
    hasMonitoringLabel: bool = Field(default=False, description="Whether namespace has openshift.io/cluster-monitoring=true label")
