import { test, expect, type Page } from '@playwright/test';

async function mockApi(page: Page) {
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
      return json({
        vllm_endpoint: 'http://mock-endpoint:8080',
        vllm_namespace: 'test-ns',
        vllm_is_name: 'small-llm-d',
      });
    }
    if (pathname === '/api/sla/profiles' && method === 'GET') {
      return json([]);
    }

    return json({});
  });
}

test('부하 테스트 탭에서 기본 폼 요소가 보임', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');

  await page.getByRole('tab', { name: 'Load Test' }).click();

  await expect(page.getByLabel('vLLM Endpoint')).toBeVisible();
  await expect(page.getByRole('button', { name: '▶ Run Load Test' })).toBeVisible();
});
