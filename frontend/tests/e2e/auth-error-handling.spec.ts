import { test, expect } from './fixtures/mock-api';

test('auth error - 401 Unauthorized redirects to /', async ({ page, mockApi }) => {
  await page.route('**/api/metrics/batch', async (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Unauthorized' }),
      });
    }
    await route.continue();
  });

  await page.goto('/metrics');

  await expect(page).toHaveURL('/');
});

test('auth error - 403 Forbidden redirects to /', async ({ page, mockApi }) => {
  await page.route('**/api/metrics/batch', async (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Forbidden' }),
      });
    }
    await route.continue();
  });

  await page.goto('/metrics');

  await expect(page).toHaveURL('/');
});

test('auth error - non-JSON 500 error does not crash app', async ({ page, mockApi }) => {
  await page.route('**/api/load_test/start', async (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({
        status: 500,
        contentType: 'text/html',
        body: '<html><body>Internal Server Error</body></html>',
      });
    }
    await route.continue();
  });

  await page.goto('/');

  await expect(page.getByRole('tab', { name: 'Load Test' })).toBeVisible();

  await page.getByRole('tab', { name: 'Load Test' }).click();
  await page.getByRole('button', { name: '▶ Run Load Test' }).click();

  await page.waitForTimeout(1000);

  await expect(page.getByRole('tab', { name: 'Load Test' })).toBeVisible();
});
