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

    if (pathname === '/api/config' && method === 'GET') {
      return json({ vllm_endpoint: '', vllm_namespace: '', vllm_is_name: '' });
    }
    if (pathname === '/api/benchmark/list' && method === 'GET') {
      return json([]);
    }
    if (pathname === '/api/metrics/batch' && method === 'POST') {
      return json({ results: {} });
    }
    if (pathname === '/api/alerts/sla-violations' && method === 'GET') {
      return json({ violations: [], has_violations: false, checked_at: 0 });
    }
    if (pathname === '/api/sla/profiles' && method === 'GET') {
      return json([]);
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
