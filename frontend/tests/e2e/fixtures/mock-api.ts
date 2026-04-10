import { test as base, expect, type Page } from '@playwright/test';

type SlaProfileState = { id: number; name: string; thresholds: Record<string, unknown>; created_at: number } | null;

export const test = base.extend<{
  mockApi: void;
}>({
  mockApi: async ({ page }, use) => {
    await setupMockApiWithState(page, () => {});
    await use();
  },
});

async function setupMockApiWithState(
  page: Page,
  setSlaState: (state: SlaProfileState) => void
) {
  let currentSlaState: SlaProfileState = null;
  const updateSlaState = (state: SlaProfileState) => {
    currentSlaState = state;
    setSlaState(state);
  };
  setSlaState(null);
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const { pathname } = new URL(req.url());
    const method = req.method();
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    // Config
    if (pathname === '/api/config' && method === 'GET') {
      return json({ vllm_endpoint: '', vllm_namespace: '', vllm_is_name: '' });
    }
    if (pathname === '/api/config' && method === 'PATCH') {
      return json({ success: true });
    }

    // Default targets (ConfigMap)
    if (pathname === '/api/config/default-targets' && method === 'GET') {
      return json({
        isvc: { name: '', namespace: '' },
        llmisvc: { name: '', namespace: '' },
        configmap_updated: false,
      });
    }
    if (pathname === '/api/config/default-targets' && method === 'PATCH') {
      return json({ success: true, configmap_updated: true });
    }

    // Benchmark
    if (pathname === '/api/benchmark/list' && method === 'GET') {
      return json([]);
    }

    // Metrics
    if (pathname === '/api/metrics/latest' && method === 'GET') {
      return json({
        status: 'ready',
        data: { tps: 100, rps: 10, kv_cache: 50, running: 5, waiting: 2, gpu_util: 60, pods: 1, pods_ready: 1 },
        hasMonitoringLabel: true,
      });
    }
    if (pathname === '/api/metrics/batch' && method === 'POST') {
      return json({ results: {} });
    }

    // Alerts
    if (pathname === '/api/alerts/sla-violations' && method === 'GET') {
      return json({ violations: [], has_violations: false, checked_at: 0 });
    }
    if (pathname === '/api/sla/profiles' && method === 'GET') {
      return json([]);
    }

    // vLLM Config
    if (pathname === '/api/vllm-config' && method === 'GET') {
      return json({
        success: true,
        data: {
          model_name: 'test-model',
          max_num_seqs: '128',
          gpu_memory_utilization: '0.85',
          max_model_len: '4096',
          max_num_batched_tokens: '1024',
          block_size: '16',
          swap_space: '2',
        },
      });
    }
    if (pathname === '/api/vllm-config' && method === 'PATCH') {
      return json({ success: true });
    }

    // Tuner
    if (pathname === '/api/tuner/status' && method === 'GET') {
      return json({ running: false, trials_completed: 0 });
    }
    if (pathname === '/api/tuner/trials' && method === 'GET') {
      return json([]);
    }
    if (pathname === '/api/tuner/importance' && method === 'GET') {
      return json({});
    }

    // Tuner - combined endpoint
    if (pathname === '/api/tuner/all' && method === 'GET') {
      return json({ status: { running: false, trials_completed: 0, best: null, status: 'idle', best_score_history: [], pareto_front_size: null, last_rollback_trial: null }, trials: [], importance: {} });
    }

    // Tuner - sessions
    if (pathname === '/api/tuner/sessions' && method === 'GET') {
      return json([]);
    }
    if (pathname.startsWith('/api/tuner/sessions/') && method === 'GET') {
      return json({});
    }
    if (pathname.startsWith('/api/tuner/sessions/') && method === 'DELETE') {
      return json({ success: true });
    }

    // Status - interrupted runs
    if (pathname === '/api/status/interrupted' && method === 'GET') {
      return json({ interrupted_runs: [] });
    }

    // Load Test
    if (pathname === '/api/load_test/start' && method === 'POST') {
      return json({ test_id: 'mock-test-id', status: 'started', message: 'Load test started', config: {} });
    }
    if (pathname === '/api/load_test/stop' && method === 'POST') {
      return json({ status: 'stopped', test_id: '', message: 'Load test stopped successfully' });
    }
    if (pathname === '/api/load_test/status' && method === 'GET') {
      return json({ test_id: null, running: false, config: null, current_result: null, elapsed: 0, sweep_result: null, is_sweeping: false });
    }
    if (pathname === '/api/load_test/history' && method === 'GET') {
      return json([]);
    }
    if (pathname === '/api/load_test/sweep' && method === 'POST') {
      return json({ status: 'running', config: {} });
    }
    if (pathname === '/api/load_test/sweep/history' && method === 'GET') {
      return json([]);
    }
    if (pathname.startsWith('/api/load_test/sweep/history/') && method === 'GET') {
      return json({});
    }
    if (pathname.startsWith('/api/load_test/sweep/history/') && method === 'DELETE') {
      return json({ status: 'deleted', sweep_id: '' });
    }
    if (pathname === '/api/load_test/sweep/save' && method === 'POST') {
      return json({ id: 'mock-sweep-id' });
    }

    // Benchmark
    if (pathname === '/api/benchmark/save' && method === 'POST') {
      return json({ id: 1, name: 'mock-benchmark', timestamp: Date.now(), config: {}, result: { success: 100, failed: 0, total: 100, tps: { mean: 100 }, latency: { p99: 0.1 }, ttft: { mean: 0.05 }, rps_actual: 10 }, metadata: {} });
    }
    if (pathname === '/api/benchmark/import' && method === 'POST') {
      return json({ imported_count: 0, benchmark_ids: [] });
    }
    if (pathname.startsWith('/api/benchmark/') && pathname.endsWith('/metadata') && method === 'PATCH') {
      return json({ id: 1, name: 'mock-benchmark', timestamp: Date.now(), config: {}, result: { success: 100, failed: 0, total: 100, tps: { mean: 100 }, latency: { p99: 0.1 }, ttft: { mean: 0.05 }, rps_actual: 10 }, metadata: {} });
    }
    if (pathname.match(/^\/api\/benchmark\/\d+$/) && method === 'GET') {
      return json({ id: 1, name: 'mock-benchmark', timestamp: Date.now(), config: {}, result: { success: 100, failed: 0, total: 100, tps: { mean: 100 }, latency: { p99: 0.1 }, ttft: { mean: 0.05 }, rps_actual: 10 }, metadata: {} });
    }
    if (pathname.match(/^\/api\/benchmark\/\d+$/) && method === 'DELETE') {
      return json({ status: 'deleted', benchmark_id: 1, message: 'Benchmark deleted successfully' });
    }

    // SLA
    if (pathname === '/api/sla/evaluate' && method === 'POST') {
      const profile = currentSlaState || { id: 1, name: 'Test SLA Profile', thresholds: { mean_tpot_max_ms: 100 }, created_at: Date.now() };
      const now = Date.now();
      return json({
        profile,
        results: [{
          benchmark_id: 1,
          benchmark_name: 'mock-benchmark',
          timestamp: now,
          verdicts: [
            { metric: 'mean_tpot', value: 45.2, threshold: 100, pass: true, status: 'pass' },
            { metric: 'p95_tpot', value: 78.3, threshold: 150, pass: true, status: 'pass' },
            { metric: 'mean_queue_time', value: 23.1, threshold: 100, pass: true, status: 'pass' },
            { metric: 'p95_queue_time', value: 45.6, threshold: 200, pass: true, status: 'pass' }
          ],
          overall_pass: true
        }],
        warnings: []
      });
    }
    if (pathname === '/api/sla/profiles' && method === 'POST') {
      currentSlaState = { id: 1, name: 'Test SLA Profile', thresholds: { mean_tpot_max_ms: 100 }, created_at: Date.now() };
      updateSlaState(currentSlaState);
      return json(currentSlaState);
    }
    if (pathname === '/api/sla/profiles' && method === 'GET') {
      return json(currentSlaState ? [currentSlaState] : []);
    }
    if (pathname.match(/^\/api\/sla\/profiles\/\d+$/) && method === 'GET') {
      return json(currentSlaState || { id: 1, name: 'Test Profile', thresholds: { mean_tpot_max_ms: 100 }, created_at: Date.now() });
    }
    if (pathname.match(/^\/api\/sla\/profiles\/\d+$/) && method === 'PUT') {
      return json({ id: 1, name: 'Updated Profile', thresholds: { mean_tpot_max_ms: 200 }, created_at: Date.now() });
    }
    if (pathname.match(/^\/api\/sla\/profiles\/\d+$/) && method === 'DELETE') {
      return json({ deleted: true });
    }

    // Metrics
    if (pathname === '/api/metrics/pods' && method === 'POST') {
      return json({ aggregated: {}, per_pod: [], pod_names: [], timestamp: 0 });
    }
    if (pathname === '/api/metrics/history' && method === 'GET') {
      return json([]);
    }
    if (pathname === '/api/metrics/pods/history' && method === 'POST') {
      return json({ results: {} });
    }

    // DESIGN DECISION: Catch-all returns json({}) instead of route.continue()
    // WHY: Test isolation - all routes are mocked, ensuring tests are deterministic
    // and don't depend on a real backend service.
    // TRADE-OFF: Real backend passthrough is not available by default.
    // OVERRIDE: If a test needs to hit the real backend for a specific endpoint,
    // add a route handler BEFORE this catch-all that calls route.continue():
    //   await page.route('**/api/specific-endpoint', async (route) => {
    //     await route.continue();
    //   });
    return json({});
  });
}

/**
 * Sets up route mocks for multi-replica display tests.
 *
 * Use this helper when testing multi-replica metrics display.
 * It overrides the default empty mocks from setupMockApi with realistic
 * multi-replica data including aggregated metrics and per-pod breakdowns.
 *
 * Unlike plain mockApi (which returns empty defaults), this provides:
 * - Batch metrics with multi-replica aggregated data
 * - Per-pod breakdown data for pod-level metrics
 * - Config with specific namespace/model for testing
 *
 * @example
 * test.beforeEach(async ({ page }) => {
 *   await setupMultiReplicaMocks(page);
 * });
 *
 * @example
 * // Custom values:
 * await setupMultiReplicaMocks(page, { namespace: 'prod', tps: 200 });
 */
export interface MultiReplicaMockOptions {
  namespace?: string;
  inferenceService?: string;
  tps?: number;
  rps?: number;
  kvCache?: number;
  running?: number;
  waiting?: number;
  gpuUtil?: number;
  gpuMemUsed?: number;
  gpuMemTotal?: number;
  pods?: number;
  podsReady?: number;
}

export async function setupMultiReplicaMocks(page: Page, options: MultiReplicaMockOptions = {}) {
  const {
    namespace = 'test-ns',
    inferenceService = 'test-model',
    tps = 150,
    rps = 15,
    kvCache = 65,
    running = 8,
    waiting = 4,
    gpuUtil = 70,
    gpuMemUsed = 14,
    gpuMemTotal = 16,
    pods = 2,
    podsReady = 2,
  } = options;

  const targetKey = `${namespace}/${inferenceService}/inferenceservice`;

  await page.route('**/api/metrics/batch', async (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: {
            [targetKey]: {
              status: 'ready',
              data: {
                tps,
                rps,
                kv_cache: kvCache,
                running,
                waiting,
                gpu_util: gpuUtil,
                gpu_mem_used: gpuMemUsed,
                gpu_mem_total: gpuMemTotal,
                pods,
                pods_ready: podsReady,
              },
              hasMonitoringLabel: true,
              history: [],
            },
          },
        }),
      });
    }
  });

  await page.route('**/api/metrics/pods', async (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          aggregated: {
            tps,
            rps,
            kv_cache: kvCache,
            running,
            waiting,
            gpu_util: gpuUtil,
            gpu_mem_used: gpuMemUsed,
            pods,
            pods_ready: podsReady,
          },
          per_pod: [
            {
              pod_name: `${inferenceService}-pod-0`,
              tps: tps * 0.67,
              rps: rps * 0.67,
              kv_cache: kvCache * 0.77,
              running: Math.floor(running * 0.375),
              waiting: Math.floor(waiting * 0.5),
              gpu_util: gpuUtil * 0.86,
              gpu_mem_used: gpuMemUsed * 0.86,
            },
            {
              pod_name: `${inferenceService}-pod-1`,
              tps: tps * 1.33,
              rps: rps * 1.33,
              kv_cache: kvCache * 1.23,
              running: Math.ceil(running * 0.625),
              waiting: Math.ceil(waiting * 0.5),
              gpu_util: gpuUtil * 1.14,
              gpu_mem_used: gpuMemTotal,
            },
          ],
        }),
      });
    }
  });

  await page.route('**/api/config', async (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          vllm_endpoint: 'http://mock-endpoint:8080',
          vllm_namespace: namespace,
          vllm_is_name: inferenceService,
        }),
      });
    }
  });
}

export { expect };
