/**
 * MockFactory - Factory methods for E2E test data consistency
 * 
 * Provides typed factory methods to create consistent mock data
 * across E2E tests, reducing duplication and ensuring data integrity.
 */

import type { SlaProfile, SlaThresholds } from '../../src/types';

/**
 * vLLM Configuration mock type
 */
export interface VllmConfigMock {
  model_name: string;
  max_num_seqs: string;
  gpu_memory_utilization: string;
  max_model_len: string;
  max_num_batched_tokens: string;
  block_size: string;
  swap_space: string;
}

/**
 * Metrics data mock type (matches MetricsData interface in mockData.ts)
 */
export interface MetricsData {
  tps: number;
  ttft_mean: number;
  latency_p99: number;
  kv_cache: number;
  running: number;
  waiting: number;
  gpu_mem_used: number;
  gpu_mem_total: number;
  pods: number;
  pods_ready: number;
  rps: number;
  ttft_p99: number;
  latency_mean: number;
  kv_hit_rate: number;
  gpu_util: number;
}

/**
 * Load test result mock type (matches LoadTestResult interface in mockData.ts)
 */
export interface LoadTestResult {
  total: number;
  success: number;
  failed: number;
  rps_actual: number;
  latency: { mean: number; p50: number; p95: number; p99: number; min: number; max: number };
  ttft: { mean: number; p95: number };
  tps: { mean: number; total: number };
}

/**
 * Cluster target mock type
 */
export interface ClusterTargetMock {
  namespace: string;
  inferenceService: string;
  crType: string;
  isDefault?: boolean;
}

/**
 * Per-pod metric snapshot
 */
export interface PerPodMetricSnapshot {
  pod_name: string;
  tps?: number;
  rps?: number;
  kv_cache?: number;
  running?: number;
  waiting?: number;
  gpu_util?: number;
  gpu_mem_used?: number;
}

/**
 * Per-pod metrics response
 */
export interface PerPodMetricsResponse {
  aggregated: MetricsData;
  per_pod: PerPodMetricSnapshot[];
  pod_names: string[];
  timestamp: number;
}

/**
 * Default values
 */
const DEFAULT_VLLM_CONFIG: VllmConfigMock = {
  model_name: 'test-model',
  max_num_seqs: '128',
  gpu_memory_utilization: '0.85',
  max_model_len: '4096',
  max_num_batched_tokens: '1024',
  block_size: '16',
  swap_space: '2',
};

const DEFAULT_METRICS_DATA: MetricsData = {
  tps: 100,
  ttft_mean: 85,
  latency_p99: 420,
  kv_cache: 50,
  running: 5,
  waiting: 2,
  gpu_mem_used: 18.4,
  gpu_mem_total: 24,
  pods: 1,
  pods_ready: 1,
  rps: 10,
  ttft_p99: 120,
  latency_mean: 300,
  kv_hit_rate: 75,
  gpu_util: 60,
};

const DEFAULT_SLA_THRESHOLDS: SlaThresholds = {
  availability_min: 99.9,
  p95_latency_max_ms: 500,
  error_rate_max_pct: 0.1,
  min_tps: 100,
};

const DEFAULT_LOAD_TEST_RESULT: LoadTestResult = {
  total: 1000,
  success: 995,
  failed: 5,
  rps_actual: 12,
  latency: { mean: 0.35, p50: 0.30, p95: 0.45, p99: 0.52, min: 0.10, max: 0.80 },
  ttft: { mean: 0.085, p95: 0.120 },
  tps: { mean: 238, total: 1480 },
};

/**
 * MockFactory - Typed factory methods for E2E test data
 */
export const MockFactory = {
  /**
   * Create a vLLM configuration mock object
   */
  createConfig(overrides?: Partial<VllmConfigMock>): VllmConfigMock {
    return { ...DEFAULT_VLLM_CONFIG, ...overrides };
  },

  /**
   * Create a metrics data mock object
   */
  createMetrics(overrides?: Partial<MetricsData>): MetricsData {
    return { ...DEFAULT_METRICS_DATA, ...overrides };
  },

  /**
   * Create an SLA profile mock object
   */
  createSlaProfile(overrides?: Partial<SlaProfile>): SlaProfile {
    return {
      id: 1,
      name: 'Test SLA Profile',
      thresholds: { ...DEFAULT_SLA_THRESHOLDS },
      created_at: Date.now(),
      ...overrides,
      thresholds: { ...DEFAULT_SLA_THRESHOLDS, ...overrides?.thresholds },
    };
  },

  /**
   * Create a load test result mock object
   */
  createLoadTestResult(overrides?: Partial<LoadTestResult>): LoadTestResult {
    return { ...DEFAULT_LOAD_TEST_RESULT, ...overrides };
  },

  /**
   * Create a cluster target mock object
   */
  createClusterTarget(overrides?: Partial<ClusterTargetMock>): ClusterTargetMock {
    return {
      namespace: 'vllm-lab-dev',
      inferenceService: 'llm-ov',
      crType: 'inferenceservice',
      isDefault: true,
      ...overrides,
    };
  },

  /**
   * Create per-pod metrics response
   */
  createPerPodMetrics(overrides?: Partial<PerPodMetricsResponse>): PerPodMetricsResponse {
    return {
      aggregated: this.createMetrics(),
      per_pod: [],
      pod_names: [],
      timestamp: Date.now(),
      ...overrides,
    };
  },

  /**
   * Create a list of cluster targets
   */
  createTargetList(targets: Partial<ClusterTargetMock>[]): ClusterTargetMock[] {
    return targets.map((t, i) => this.createClusterTarget({ ...t, isDefault: i === 0 }));
  },
};
