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

    return json({});
  });
}

test('튜너 탭에서 시작 폼 렌더링', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');

  await page.getByRole('tab', { name: '자동 파라미터 튜닝' }).click();

  await expect(page.getByText('Bayesian Optimization 설정')).toBeVisible();
  await expect(page.getByLabel('완료 후 벤치마크 자동 저장')).toBeVisible();
});
