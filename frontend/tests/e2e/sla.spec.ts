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
    if (pathname === '/api/sla/profiles' && method === 'GET') {
      return json([]);
    }
    if (pathname === '/api/alerts/sla-violations' && method === 'GET') {
      return json({ violations: [], has_violations: false, checked_at: 0 });
    }

    return json({});
  });
}

test('SLA 탭에서 프로필 목록 렌더링', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');

  await page.getByRole('tab', { name: 'SLA' }).click();

  await expect(page.getByText('새 SLA 프로필 생성')).toBeVisible();
  await expect(page.getByText('SLA 프로필 목록')).toBeVisible();
});
