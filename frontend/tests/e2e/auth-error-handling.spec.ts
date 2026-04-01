import { test, expect, type Page } from '@playwright/test';

async function mockApiWithError(page: Page, status: number, body?: string, contentType = 'application/json') {
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const { pathname } = new URL(req.url());

    if (pathname === '/api/metrics/batch' && req.method() === 'POST') {
      return route.fulfill({
        status,
        contentType,
        body: body || JSON.stringify({ detail: 'Unauthorized' }),
      });
    }

    if (pathname === '/api/config' && req.method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ vllm_endpoint: '', vllm_namespace: '', vllm_is_name: '' }),
      });
    }

    if (pathname === '/api/sla/profiles' && req.method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });
}

test('auth error - 401 Unauthorized redirects to /', async ({ page }) => {
  await mockApiWithError(page, 401);
  await page.goto('/metrics');

  await expect(page).toHaveURL('/');
});

test('auth error - 403 Forbidden redirects to /', async ({ page }) => {
  await mockApiWithError(page, 403);
  await page.goto('/metrics');

  await expect(page).toHaveURL('/');
});

test('auth error - non-JSON 500 error does not crash app', async ({ page }) => {
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const { pathname } = new URL(req.url());

    if (pathname === '/api/config' && req.method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ vllm_endpoint: '', vllm_namespace: '', vllm_is_name: '' }),
      });
    }

    if (pathname === '/api/sla/profiles' && req.method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    }

    if (pathname === '/api/load_test/start' && req.method() === 'POST') {
      return route.fulfill({
        status: 500,
        contentType: 'text/html',
        body: '<html><body>Internal Server Error</body></html>',
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });

  await page.goto('/');

  await expect(page.getByRole('tab', { name: 'Load Test' })).toBeVisible();

  await page.getByRole('tab', { name: 'Load Test' }).click();
  await page.getByRole('button', { name: '▶ Run Load Test' }).click();

  await page.waitForTimeout(1000);

  await expect(page.getByRole('tab', { name: 'Load Test' })).toBeVisible();
});
