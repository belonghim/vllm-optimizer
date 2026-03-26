interface MetricsData {
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

export const mockMetrics = (): MetricsData => ({
  tps: 245 + Math.random() * 50,
  ttft_mean: 85 + Math.random() * 30,
  latency_p99: 420 + Math.random() * 80,
  kv_cache: 67 + Math.random() * 10,
  running: Math.floor(15 + Math.random() * 10),
  waiting: Math.floor(Math.random() * 5),
  gpu_mem_used: 18.4, gpu_mem_total: 24,
  pods: 3, pods_ready: 3,
  rps: 12 + Math.random() * 8,
  ttft_p99: 120 + Math.random() * 50,
  latency_mean: 300 + Math.random() * 60,
  kv_hit_rate: Math.random() * 100,
  gpu_util: 40 + Math.random() * 40,
});

interface HistoryPoint {
  t: string;
  tps: number;
  ttft: number;
  lat_p99: number;
  kv: number;
  running: number;
  waiting: number;
  rps: number;
  ttft_p99: number;
  lat_mean: number;
  kv_hit: number;
  gpu_util: number;
  gpu_mem_used: number;
  gpu_mem_total: number;
}

export const mockHistory = (): HistoryPoint[] => Array.from({ length: 60 }, (_, i) => ({
  t: `${String(Math.floor(i / 4)).padStart(2, "0")}:${String((i % 4) * 15).padStart(2, "0")}`,
  tps: 220 + Math.random() * 80, ttft: 80 + Math.random() * 40,
  lat_p99: 380 + Math.random() * 120, kv: 60 + Math.random() * 20,
  running: 10 + Math.random() * 15, waiting: Math.random() * 8,
  rps: 10 + Math.random() * 10,
  ttft_p99: 100 + Math.random() * 60,
  lat_mean: 280 + Math.random() * 80,
  kv_hit: Math.random() * 100,
  gpu_util: 35 + Math.random() * 45,
  gpu_mem_used: 18.4,
  gpu_mem_total: 24,
}));

interface BenchmarkMetadata {
  model_identifier?: string;
  hardware_type?: string;
  runtime?: string;
  vllm_version?: string;
  replica_count?: number;
  notes?: string;
  extra?: Record<string, string>;
}

interface BenchmarkResult {
  tps: { mean: number };
  latency: { p99: number };
  rps_actual: number;
  ttft: { mean: number };
  gpu_utilization_avg: number;
}

interface BenchmarkConfig {
  model: string;
  endpoint: string;
  total_requests: number;
  concurrency: number;
}

interface Benchmark {
  id: number;
  name: string;
  timestamp: number;
  config: BenchmarkConfig;
  result: BenchmarkResult;
  metadata: BenchmarkMetadata;
}

export const mockBenchmarks = (): Benchmark[] => [
  {
    id: 1,
    name: "Baseline (default)",
    timestamp: Date.now() / 1000 - 86400,
    config: {
      model: "Qwen2.5-3B",
      endpoint: "http://llm-ov-predictor.vllm.svc.cluster.local:8080",
      total_requests: 200,
      concurrency: 20
    },
    result: { tps: { mean: 180 }, latency: { p99: 0.52 }, rps_actual: 12, ttft: { mean: 0.095 }, gpu_utilization_avg: 45 },
    metadata: {
      model_identifier: "phi-4-mini-instruct",
      hardware_type: "CPU",
      runtime: "OpenVINO",
      vllm_version: "0.6.2",
      replica_count: 1,
      notes: "Default baseline on OpenShift Dev",
      extra: { "source": "modelcar" }
    }
  },
  {
    id: 2,
    name: "max_num_seqs=256",
    timestamp: Date.now() / 1000 - 3600,
    config: {
      model: "Llama-3.1-8B",
      endpoint: "http://llm-ov-predictor.vllm.svc.cluster.local:8080",
      total_requests: 200,
      concurrency: 20
    },
    result: { tps: { mean: 247 }, latency: { p99: 0.41 }, rps_actual: 18, ttft: { mean: 0.078 }, gpu_utilization_avg: 62 },
    metadata: {
      model_identifier: "llama-3.1-8b-instruct",
      hardware_type: "GPU",
      notes: "Tested with larger batch size"
    }
  },
  {
    id: 3,
    name: "chunked_prefill=on",
    timestamp: Date.now() / 1000 - 1800,
    config: {
      model: "Mistral-7B",
      endpoint: "http://llm-ov-predictor.vllm.svc.cluster.local:8080",
      total_requests: 200,
      concurrency: 20
    },
    result: { tps: { mean: 265 }, latency: { p99: 0.38 }, rps_actual: 20, ttft: { mean: 0.072 }, gpu_utilization_avg: 38 },
    metadata: {
      vllm_version: "0.6.3.dev",
      notes: "Chunked prefill optimization test"
    }
  },
];

interface TrialParams {
  max_num_seqs: number;
  gpu_memory_utilization: number;
}

interface Trial {
  id: number;
  tps: number;
  p99_latency: number;
  score: number;
  params: TrialParams;
  status: string;
}

export const mockTrials = (): Trial[] => Array.from({ length: 12 }, (_, i) => ({
  id: i, tps: 150 + Math.random() * 150, p99_latency: 300 + Math.random() * 400,
  score: Math.random() * 100,
  params: { max_num_seqs: [64,128,256,512][i%4], gpu_memory_utilization: 0.8 + Math.random() * 0.15 },
  status: "completed",
}));

interface HistoryWithGapsPoint {
  t: string;
  tps: number;
  ttft: number | null;
  lat_p99: number | null;
  kv: number;
  running: number;
  waiting: number;
  rps: number;
  ttft_p99: number | null;
  lat_mean: number | null;
  kv_hit: number;
  gpu_util: number;
  gpu_mem_used: number;
  gpu_mem_total: number;
}

export const mockHistoryWithGaps = (): HistoryWithGapsPoint[] => Array.from({ length: 60 }, (_, i) => {
  const isGap = (i >= 10 && i < 25) || (i >= 35 && i < 45);
  return {
    t: `${String(Math.floor(i / 4)).padStart(2, "0")}:${String((i % 4) * 15).padStart(2, "0")}`,
    tps: 220 + Math.random() * 80,
    ttft: isGap ? null : 80 + Math.random() * 40,
    lat_p99: isGap ? null : 380 + Math.random() * 120,
    kv: 60 + Math.random() * 20,
    running: 10 + Math.random() * 15,
    waiting: Math.random() * 8,
    rps: 10 + Math.random() * 10,
    ttft_p99: isGap ? null : 100 + Math.random() * 60,
    lat_mean: isGap ? null : 280 + Math.random() * 80,
    kv_hit: Math.random() * 100,
    gpu_util: 35 + Math.random() * 45,
    gpu_mem_used: 18.4,
    gpu_mem_total: 24,
  };
});

interface LoadTestResult {
  total: number;
  success: number;
  failed: number;
  rps_actual: number;
  latency: { mean: number; p50: number; p95: number; p99: number; min: number; max: number };
  ttft: { mean: number; p95: number };
  tps: { mean: number; total: number };
}

interface LatencyDataPoint {
  t: number;
  lat: number;
  tps: number;
}

interface LoadTestConfig {
  total_requests: number;
}

export const simulateLoadTest = (
  config: LoadTestConfig,
  setProgress: (progress: number) => void,
  setResult: (result: LoadTestResult) => void,
  setStatus: (status: string) => void,
  setLatencyData: (fn: (prev: LatencyDataPoint[]) => LatencyDataPoint[]) => void
): void => {
  let done = 0;
  const id = setInterval(() => {
    done += Math.floor(Math.random() * 8) + 2;
    if (done >= config.total_requests) done = config.total_requests;
    setProgress(Math.round((done / config.total_requests) * 100));
    setLatencyData(prev => [...prev.slice(-60), {
      t: prev.length, lat: 350 + Math.random() * 150, tps: 200 + Math.random() * 80
    }]);
    setResult({
      total: done, success: done - Math.floor(done * 0.005), failed: Math.floor(done * 0.005),
      rps_actual: 12 + Math.random() * 4,
      latency: { mean: 0.35, p50: 0.30, p95: 0.45, p99: 0.52, min: 0.10, max: 0.80 },
      ttft: { mean: 0.085, p95: 0.120 },
      tps: { mean: 238, total: 1480 },
    });
    if (done >= config.total_requests) { setStatus("completed"); clearInterval(id); }
  }, 200);
};
