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

test('벤치마크 탭에서 목록 조회', async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => {
    window.localStorage.setItem('vllm-opt-mock-enabled', 'false');
  });
  await page.goto('/');

  await page.getByRole('tab', { name: '벤치마크 비교' }).click();

  await expect(page.getByText('부하 테스트 결과를 저장하면 여기 나타납니다.')).toBeVisible();
});
