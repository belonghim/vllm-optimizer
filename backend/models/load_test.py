"""
Pydantic models for vLLM Optimizer API

This module defines all data models used for API request/response validation
and internal data structures. Models are divided into:
- Load test configuration and results
- Performance statistics
- Auto-tuning configuration and trial results
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SyntheticPromptConfig(BaseModel):
    """Synthetic prompt generation configuration"""

    distribution: Literal["uniform", "normal"] = Field(
        default="uniform", description="Distribution type: 'uniform' or 'normal'"
    )
    min_tokens: int = Field(default=50, ge=1, description="Minimum approximate token count")
    max_tokens: int = Field(default=500, ge=1, description="Maximum approximate token count")
    mean_tokens: int | None = Field(default=None, ge=1, description="Mean tokens for normal distribution")
    stddev_tokens: int | None = Field(default=None, ge=1, description="Std dev tokens for normal distribution")


class LoadTestConfig(BaseModel):
    """Load test configuration"""

    endpoint: str = Field(
        default="", description="vLLM endpoint URL (empty = use server default from VLLM_ENDPOINT env)"
    )
    model: str = Field(default="auto", description="Model name")
    prompt_template: str = Field(default="Hello, how are you?", description="Prompt for generation")
    total_requests: int = Field(default=100, ge=1, description="Total number of requests")
    concurrency: int = Field(default=10, ge=1, le=1000, description="Concurrent requests")
    duration: int = Field(default=30, ge=1, le=3600, description="Test duration in seconds (max 1 hour)")
    rps: int = Field(default=0, ge=0, le=10000, description="Requests per second (0=unlimited)")
    max_tokens: int = Field(default=256, ge=1, le=8192, description="Max tokens to generate")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Temperature for generation")
    stream: bool = Field(default=True, description="Enable streaming mode")
    prompt_mode: str = Field(default="static", description="Prompt mode: 'static' or 'synthetic'")
    endpoint_type: str = Field(default="completions", description="API endpoint type: 'completions' or 'chat'")
    synthetic_config: SyntheticPromptConfig | None = Field(
        default=None, description="Synthetic prompt config (used when prompt_mode='synthetic')"
    )


class RequestResult(BaseModel):
    """Single request result"""

    req_id: int
    success: bool
    latency: float = Field(description="Total latency in seconds")
    ttft: float | None = Field(default=None, description="Time to first token in seconds")
    output_tokens: int = Field(default=0, description="Number of output tokens")
    tps: float = Field(default=0.0, description="Tokens per second")
    error: str | None = Field(default=None, description="Error message if failed")
    token_timestamps: list[float] | None = Field(
        default=None, description="Per-token receive timestamps (epoch seconds), streaming only"
    )
    itl_deltas: list[float] | None = Field(
        default=None,
        description="Raw per-token inter-arrival deltas in seconds (streaming only)",
    )
    itl_mean: float | None = Field(default=None, description="Mean inter-token latency in seconds")
    itl_p50: float | None = Field(default=None, description="P50 inter-token latency in seconds")
    itl_p95: float | None = Field(default=None, description="P95 inter-token latency in seconds")
    itl_p99: float | None = Field(default=None, description="P99 inter-token latency in seconds")
    time_per_output_token: float | None = Field(default=None, description="Time per output token in seconds")
    queue_time: float | None = Field(default=None, description="Queue wait time in seconds")


class ErrorResponse(BaseModel):
    """Standard error response model"""

    success: bool = False
    error: str
    error_type: str | None = None
    detail: dict[str, Any] | None = None


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
    gpu_utilization_avg: float | None = 0.0
    tokens_per_sec: float = 0.0
    metrics_target_matched: bool = Field(
        default=True,
        description="GPU 메트릭 수집 대상이 부하 테스트 대상과 일치하는지 여부 (불일치 시 GPU Eff. 계산값이 무의미)",
    )
    itl: dict | None = Field(
        default=None, description="Aggregated ITL stats: {mean, p50, p95, p99} in seconds. None for non-streaming."
    )
    tpot: LatencyStats | None = Field(default=None, description="Time per output token stats")
    queue_time: LatencyStats | None = Field(default=None, description="Queue wait time stats")


class SweepConfig(BaseModel):
    endpoint: str = Field(default="", description="vLLM endpoint URL")
    model: str = Field(default="auto", description="Model name")
    rps_start: int = Field(default=1, ge=1, description="Starting RPS")
    rps_end: int = Field(default=50, ge=1, description="Ending RPS")
    rps_step: int = Field(default=5, ge=1, description="RPS increment per step")
    requests_per_step: int = Field(default=20, ge=1, description="Requests per step")
    concurrency: int = Field(default=10, ge=1, description="Concurrent requests")
    max_tokens: int = Field(default=128, ge=1, description="Max tokens per request")
    stream: bool = Field(default=True, description="Enable streaming")
    prompt: str = Field(default="Explain quantum computing in simple terms", description="Request prompt")
    saturation_error_rate: float = Field(
        default=0.1, ge=0.0, le=1.0, description="Error rate threshold for saturation detection"
    )
    saturation_latency_factor: float = Field(
        default=3.0, ge=1.0, description="P99 latency multiple vs step-1 for saturation detection"
    )
    min_stable_steps: int = Field(default=1, ge=1, description="Consecutive saturated steps required to stop sweep")


class SweepStepResult(BaseModel):
    step: int = Field(description="Step number (1-indexed)")
    rps: float = Field(description="Target RPS for this step")
    stats: dict = Field(default_factory=dict, description="Load test stats for this step")
    saturated: bool = Field(default=False, description="Whether saturation was detected at this step")
    saturation_reason: str | None = Field(default=None, description="Reason for saturation if detected")


class SweepResult(BaseModel):
    config: SweepConfig
    steps: list[SweepStepResult] = Field(default_factory=list)
    saturation_point: float | None = Field(default=None, description="RPS at which saturation was first detected")
    optimal_rps: float | None = Field(default=None, description="Last non-saturated RPS (recommended operating point)")
    total_duration: float = Field(default=0.0, description="Total sweep duration in seconds")


class TuningConfig(BaseModel):
    """Configuration for auto-tuning parameters"""

    # Search space ranges
    max_num_seqs_range: tuple[int, int] = Field(default=(64, 512), description="Range for max-num-seqs parameter")
    gpu_memory_utilization_range: tuple[float, float] = Field(
        default=(0.80, 0.95), description="Range for GPU memory utilization"
    )
    max_model_len_range: tuple[int, int] = Field(default=(2048, 8192), description="Range for max-model-len parameter")
    # Expanded search space and tuning controls
    max_num_batched_tokens_range: tuple[int, int] = Field(
        default=(256, 2048), description="Range for max-num-batched-tokens parameter"
    )
    block_size_options: list[int] = Field(default=[8, 16, 32], description="KV cache block size options")
    include_swap_space: bool = Field(
        default=False, description="Enable swap_space parameter search (disable on CPU/OpenVINO)"
    )
    swap_space_range: tuple[float, float] = Field(default=(1.0, 8.0), description="Range for swap-space parameter (GB)")
    eval_concurrency: int = Field(
        default=16, ge=1, le=128, description="Concurrent requests during evaluation load test"
    )
    eval_rps: int = Field(default=20, ge=0, le=500, description="Requests per second during evaluation (0=unlimited)")
    eval_fast_fraction: float = Field(
        default=0.5, ge=0.1, le=1.0, description="Fraction of eval_requests for MedianPruner fast probe"
    )
    # Optimization objectives
    objective: str = Field(default="tps", description="Optimization objective: tps, latency, or balanced")
    n_trials: int = Field(default=10, ge=1, le=100, description="Number of optimization trials")
    warmup_requests: int = Field(default=20, ge=0, description="Number of warmup requests per trial")
    eval_requests: int = Field(default=100, ge=1, le=1000, description="Number of evaluation requests per trial")

    @model_validator(mode="after")
    def validate_ranges(self) -> "TuningConfig":
        ranges = {
            "max_num_seqs_range": self.max_num_seqs_range,
            "gpu_memory_utilization_range": self.gpu_memory_utilization_range,
            "max_model_len_range": self.max_model_len_range,
            "max_num_batched_tokens_range": self.max_num_batched_tokens_range,
            "swap_space_range": self.swap_space_range,
        }
        for name, r in ranges.items():
            if r[0] >= r[1]:
                raise ValueError(f"{name}: min({r[0]}) must be less than max({r[1]})")
        return self


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
    ttft_mean: float | None = Field(default=None, description="Time to first token (mean) in ms")
    ttft_p99: float | None = Field(default=None, description="Time to first token (P99) in ms")
    latency_mean: float | None = Field(default=None, description="End-to-end latency (mean) in ms")
    latency_p99: float | None = Field(default=None, description="End-to-end latency (P99) in ms")
    kv_cache: float = Field(default=0.0, description="KV cache usage percentage")
    kv_hit_rate: float = Field(default=0.0, description="KV cache hit rate")
    running: int = Field(default=0, description="Number of currently running requests")
    waiting: int = Field(default=0, description="Number of requests waiting in queue")
    gpu_mem_used: float = Field(default=0.0, description="GPU memory used in GB")
    gpu_mem_total: float = Field(default=0.0, description="Total GPU memory in GB")
    gpu_util: float = Field(default=0.0, description="GPU utilization percentage")
    pods: int = Field(default=0, description="Total number of vLLM pods")
    pods_ready: int = Field(default=0, description="Number of ready vLLM pods")
    tpot_mean: float | None = Field(default=None, description="Time per output token (mean) in ms")
    tpot_p99: float | None = Field(default=None, description="Time per output token (P99) in ms")
    queue_time_mean: float | None = Field(default=None, description="Queue wait time (mean) in ms")
    queue_time_p99: float | None = Field(default=None, description="Queue wait time (P99) in ms")


class PerPodMetricSnapshot(BaseModel):
    """Per-pod metrics snapshot for individual pod monitoring"""

    pod_name: str
    tps: float | None
    rps: float | None
    kv_cache: float | None
    running: int | None
    waiting: int | None
    gpu_util: float | None
    gpu_mem_used: float | None
    gpu_mem_total: float | None


class PerPodMetricsResponse(BaseModel):
    """Response model containing aggregated and per-pod metrics"""

    aggregated: MetricsSnapshot
    per_pod: list[PerPodMetricSnapshot]
    pod_names: list[str]
    timestamp: float


class BenchmarkMetadata(BaseModel):
    model_identifier: str | None = Field(
        default=None, description="모델 식별자 (자동 수집 시 서빙 이름, 사용자가 실제 모델명으로 편집 가능)"
    )
    hardware_type: str | None = Field(default=None, description="하드웨어 타입 (예: CPU, GPU-A100)")
    runtime: str | None = Field(default=None, description="런타임 (예: OpenVINO, CUDA)")
    vllm_version: str | None = Field(default=None, description="vLLM 버전")
    replica_count: int | None = Field(default=None, description="레플리카 수")
    notes: str | None = Field(default=None, description="사용자 메모")
    extra: dict[str, str] = Field(default_factory=dict, description="사용자 자유 key-value (문자열 쌍)")
    source: str | None = Field(
        default=None, description="Benchmark source: None=native, 'guidellm'=imported from GuideLLM"
    )


class Benchmark(BaseModel):
    """Saved benchmark result for comparison"""

    id: int | None = Field(default=None, description="Unique benchmark identifier")
    name: str = Field(description="User-provided benchmark name")
    timestamp: float | None = Field(default=None, description="Unix timestamp when benchmark was saved")
    config: LoadTestConfig = Field(description="Load test configuration used")
    result: LoadTestResult = Field(description="Final load test results")
    metadata: BenchmarkMetadata | None = Field(default=None)


class TargetedMetricsResponse(BaseModel):
    """Response for targeted metrics queries via namespace + is_name."""

    status: str = Field(description='"collecting" if metrics not yet available, "ready" if data present')
    data: MetricsSnapshot | None = Field(
        default=None, description="Latest metrics snapshot, null when status is collecting"
    )
    hasMonitoringLabel: bool = Field(
        default=False, description="Whether namespace has openshift.io/cluster-monitoring=true label"
    )
    crExists: bool | None = Field(
        default=None,
        description="Whether the CR still exists in K8s. None = not yet checked, True = exists, False = deleted",
    )


class MetricsTarget(BaseModel):
    """Single target for batch metrics query."""

    namespace: str = Field(description="Kubernetes namespace")
    inferenceService: str = Field(description="InferenceService name")
    cr_type: str | None = Field(default=None, description="CR type: inferenceservice or llminferenceservice")


class BatchMetricsRequest(BaseModel):
    """Request body for batch metrics endpoint."""

    targets: list[MetricsTarget] = Field(description="List of targets to query")
    history_points: int = Field(default=150, ge=1, le=1000, description="Number of history points to return per target")
    time_range: str | None = Field(
        default=None, description="Time range: 6h, 24h, 7d — uses Thanos query_range instead of in-memory buffer"
    )
    metrics_source: Literal["direct", "thanos"] | None = Field(
        default=None,
        description="Metrics collection source: 'direct' (vLLM pod scrape) or 'thanos' (Thanos Querier). No fallback is applied when omitted.",
    )


class BatchMetricsResponse(BaseModel):
    """Response for batch metrics queries."""

    results: dict[str, dict[str, Any]] = Field(description="Mapping of ns/is to data and status")


class TuningSessionSummary(BaseModel):
    id: int
    timestamp: float
    objective: str
    n_trials: int
    best_tps: float | None
    best_p99: float | None
    best_score: float | None


class TuningSessionDetail(TuningSessionSummary):
    best_params: dict | None = None
    trials: list[dict]
    importance: dict
