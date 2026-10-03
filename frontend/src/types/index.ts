export interface SlaThresholds {
  availability_min: number | null;
  p95_latency_max_ms: number | null;
  error_rate_max_pct: number | null;
  mean_ttft_max_ms?: number | null;
  p95_ttft_max_ms?: number | null;
  mean_e2e_latency_max_ms?: number | null;
  mean_tpot_max_ms?: number | null;
  p95_tpot_max_ms?: number | null;
  mean_queue_time_max_ms?: number | null;
  p95_queue_time_max_ms?: number | null;
}

export interface SlaProfile {
  id: number;
  name: string;
  thresholds: SlaThresholds;
  created_at: number;
}

export interface HistoryPoint {
  timestamp: number;
  tps?: number;
  ttft_mean?: number;
  latency_p99?: number;
  kv_cache?: number;
  running?: number;
  waiting?: number;
  rps?: number;
  ttft_p99?: number;
  latency_mean?: number;
  kv_hit_rate?: number;
  gpu_util?: number;
  gpu_mem_used?: number;
  gpu_mem_total?: number;
  tpot_mean?: number | null;
  tpot_p99?: number | null;
  queue_time_mean?: number | null;
  queue_time_p99?: number | null;
}

export interface TargetResultData {
  tps?: number | null;
  latency_p99?: number | null;
  latency_mean?: number | null;
  ttft_mean?: number | null;
  ttft_p99?: number | null;
  kv_cache?: number | null;
  kv_hit_rate?: number | null;
  running?: number | null;
  waiting?: number | null;
  rps?: number | null;
  gpu_util?: number | null;
  gpu_mem_used?: number | null;
  gpu_mem_total?: number | null;
  tpot_mean?: number | null;
  tpot_p99?: number | null;
  queue_time_mean?: number | null;
  queue_time_p99?: number | null;
  error_rate?: number | null;
  availability?: number | null;
}

export interface PerPodMetricSnapshot {
  pod_name: string;
  tps?: number | null;
  rps?: number | null;
  kv_cache?: number | null;
  running?: number | null;
  waiting?: number | null;
  gpu_util?: number | null;
  gpu_mem_used?: number | null;
  gpu_mem_total?: number | null;
}

export interface PerPodMetricsResponse {
  aggregated: TargetResultData;
  per_pod: PerPodMetricSnapshot[];
  pod_names: string[];
  timestamp: number;
}

export type PerPodMetricsDict = Record<string, PerPodMetricsResponse>;

export interface TargetResult {
  status: string;
  error?: string;
  data?: TargetResultData | null;
  history?: HistoryPoint[];
  hasMonitoringLabel?: boolean;
  crExists?: boolean | null;
}

export interface TargetState {
  status?: string;
  data?: TargetResultData | null;
  metrics?: TargetResultData | null;
  history?: Record<string, unknown>[];
  hasMonitoringLabel?: boolean;
  crExists?: boolean | null;
  error?: string | null;
}

export interface ClusterTarget {
  namespace: string;
  inferenceService: string;
  crType: string;
  source?: 'configmap' | 'manual';
  modelName?: string;
}

export interface ClusterConfig {
  version: number;
  endpoint: string;
  targets: ClusterTarget[];
}

export interface SSEState {
  status: 'idle' | 'running' | 'completed' | 'error' | 'stopped';
  isReconnecting: boolean;
  retryCount: number;
  error: string | null;
}

export interface SSEErrorPayload {
  error: string;
  error_type?: string;
}

export interface SSEWarningPayload {
  message: string;
  trial?: number;
}

export interface TunerPhase {
  trial_id: number;
  phase: string;
}

export interface TunerStatus {
  running: boolean;
  trials_completed: number;
  best?: {
    tps: number;
    p99_latency: number;
    params?: Record<string, unknown>;
  };
  best_score_history?: number[];
}

export interface TunerTrial {
  id: number;
  tps: number;
  p99_latency: number;
  score: number;
  params: Record<string, unknown>;
  status: string;
  is_pareto_optimal?: boolean;
}

export interface BenchmarkMetadata {
  model_identifier?: string | null;
  hardware_type?: string | null;
  runtime?: string | null;
  vllm_version?: string | null;
  replica_count?: number | null;
  notes?: string | null;
  extra?: Record<string, string>;
  source?: string | null;
}

export interface BenchmarkRunConfig {
  model?: string;
  [key: string]: unknown;
}

export interface BenchmarkResultData {
  tps?: { mean?: number } | null;
  latency?: { p99?: number } | null;
  ttft?: { mean?: number } | null;
  rps_actual?: number;
  gpu_utilization_avg?: number | null;
  metrics_target_matched?: boolean;
}

export interface LoadTestMetricStats {
  mean?: number | null;
  p50?: number | null;
  p95?: number | null;
  p99?: number | null;
  total?: number | null;
  min?: number | null;
  max?: number | null;
}

export interface LoadTestResult {
  total?: number;
  total_requested?: number;
  success?: number;
  failed?: number;
  rps_actual?: number;
  tps?: LoadTestMetricStats | null;
  ttft?: LoadTestMetricStats | null;
  latency?: LoadTestMetricStats | null;
  gpu_utilization_avg?: number | null;
  metrics_target_matched?: boolean;
  [key: string]: unknown;
}

export interface BenchmarkItem {
  id: string | number;
  name: string;
  timestamp: number;
  config?: BenchmarkRunConfig;
  result: BenchmarkResultData;
  metadata?: BenchmarkMetadata | null;
}

export interface TunerConfig {
  objective: string;
  evaluation_mode: 'single' | 'sweep';
  n_trials: number;
  vllm_endpoint: string;
  max_num_seqs_min: number;
  max_num_seqs_max: number;
  gpu_memory_min: number;
  gpu_memory_max: number;
  max_model_len_min: number;
  max_model_len_max: number;
  max_num_batched_tokens_min: number;
  max_num_batched_tokens_max: number;
  block_size_options: number[];
  include_swap_space: boolean;
  swap_space_min: number;
  swap_space_max: number;
  eval_concurrency: number;
  eval_rps: number;
  eval_requests: number;
  enable_llm_assistant?: boolean;
  p99_latency_sla_ms?: number | null;
  accelerator_memory_gib?: number | null;
}

export interface TuningWarmupSuggestionsPayload {
  count: number;
  configurations: Record<string, unknown>[];
}

export interface TuningFailureExplanationPayload {
  trial_id: number;
  reason: string;
  explanation: string;
}

export interface TuningReportPayload {
  markdown: string;
  summary?: Record<string, unknown>;
}

export interface ModelAnalysisModel {
  architecture: string | null;
  model_type: string | null;
  multimodal: boolean;
  num_hidden_layers: number | null;
  full_attention_layers: number;
  sliding_attention_layers: number;
  linear_attention_layers: number;
  kv_shared_layers: number;
  num_attention_heads: number | null;
  num_key_value_heads: number | null;
  head_dim: number | null;
  full_attention_head_dim: number | null;
  mla: boolean;
  sliding_window: number | null;
  max_position_embeddings: number | null;
  num_experts: number | null;
  num_experts_per_tok: number | null;
  weight_dtype: string | null;
  quantization: string | null;
  kv_cache_dtype: string;
  kv_dtype_bytes: number;
  kv_bytes_per_token: number | null;
  sliding_kv_bytes_per_token: number;
  linear_state_bytes_per_seq: number;
  model_weight_gib: number | null;
  served_model_name: string | null;
  served_max_model_len: number | null;
  warnings: string[];
}

export interface ModelCapacityRow {
  context_len: number;
  kv_bytes_per_seq: number;
  max_concurrent_seqs: number;
}

export interface SuggestedSearchSpace {
  max_num_seqs_min: number;
  max_num_seqs_max: number;
  max_model_len_min: number;
  max_model_len_max: number;
}

export interface ModelAnalysis {
  target: { namespace: string; name: string; cr_type: string };
  available: boolean;
  model: ModelAnalysisModel | null;
  runtime: {
    gpu_count?: number;
    tensor_parallel_size?: number | null;
    kv_cache_dtype?: string;
    current_args?: Record<string, unknown>;
  };
  memory_budget: {
    gib?: number | null;
    source?: string;
    utilization?: number | null;
    dedicated_kv?: boolean;
  };
  capacity: ModelCapacityRow[];
  suggested_search_space: SuggestedSearchSpace | null;
  analyst_available: boolean;
  warnings: string[];
}
