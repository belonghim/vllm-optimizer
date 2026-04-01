export interface SlaThresholds {
  availability_min: number | null;
  p95_latency_max_ms: number | null;
  error_rate_max_pct: number | null;
  min_tps: number | null;
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
}

export interface PerPodMetricsResponse {
  aggregated: TargetResultData;
  per_pod: PerPodMetricSnapshot[];
  pod_names: string[];
  timestamp: number;
}

export interface TargetResult {
  status: string;
  error?: string;
  data?: TargetResultData | null;
  history?: HistoryPoint[];
  hasMonitoringLabel?: boolean;
}

export interface TargetState {
  status?: string;
  data?: TargetResultData | null;
  metrics?: TargetResultData | null;
  history?: Record<string, unknown>[];
  hasMonitoringLabel?: boolean;
  error?: string | null;
}

export interface ClusterTarget {
  namespace: string;
  inferenceService: string;
  isDefault: boolean;
  crType?: string;
}

export interface ClusterConfig {
  version: number;
  endpoint: string;
  targets: ClusterTarget[];
  maxTargets: number;
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

export interface TunerConfig {
  objective: string;
  evaluation_mode: "single" | "sweep";
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
}
