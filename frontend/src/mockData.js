export const mockMetrics = () => ({
  tps: 245 + Math.random() * 50,
  ttft_mean: 85 + Math.random() * 30,
  latency_p99: 420 + Math.random() * 80,
  kv_cache: 67 + Math.random() * 10,
  running: Math.floor(15 + Math.random() * 10),
  waiting: Math.floor(Math.random() * 5),
  gpu_mem_used: 18.4, gpu_mem_total: 24,
  pods: 3, pods_ready: 3,
});

export const mockHistory = () => Array.from({ length: 60 }, (_, i) => ({
  t: `${String(Math.floor(i / 4)).padStart(2, "0")}:${String((i % 4) * 15).padStart(2, "0")}`,
  tps: 220 + Math.random() * 80, ttft: 80 + Math.random() * 40,
  lat_p99: 380 + Math.random() * 120, kv: 60 + Math.random() * 20,
  running: 10 + Math.random() * 15, waiting: Math.random() * 8,
}));

export const mockBenchmarks = () => [
  { id: 1, name: "Baseline (default)", timestamp: Date.now() / 1000 - 86400,
    result: { tps: { mean: 180 }, latency: { p99: 0.52 }, rps_actual: 12, ttft: { mean: 0.095 } }},
  { id: 2, name: "max_num_seqs=256", timestamp: Date.now() / 1000 - 3600,
    result: { tps: { mean: 247 }, latency: { p99: 0.41 }, rps_actual: 18, ttft: { mean: 0.078 } }},
  { id: 3, name: "chunked_prefill=on", timestamp: Date.now() / 1000 - 1800,
    result: { tps: { mean: 265 }, latency: { p99: 0.38 }, rps_actual: 20, ttft: { mean: 0.072 } }},
];

export const mockTrials = () => Array.from({ length: 12 }, (_, i) => ({
  id: i, tps: 150 + Math.random() * 150, p99_latency: 300 + Math.random() * 400,
  score: Math.random() * 100,
  params: { max_num_seqs: [64,128,256,512][i%4], gpu_memory_utilization: 0.8 + Math.random() * 0.15 },
  status: "completed",
}));

export const simulateLoadTest = (config, setProgress, setResult, setStatus, setLatencyData) => {
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
