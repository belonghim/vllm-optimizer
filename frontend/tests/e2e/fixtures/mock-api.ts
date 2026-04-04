import { test as base, expect, type Page } from '@playwright/test';

export async function setupMockApi(page: Page) {
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

    return json({});
  });
}

export const test = base.extend<{ mockApi: void }>({
  mockApi: async ({ page }, next) => {
    await setupMockApi(page);
    await next();
  },
});

export { expect };
