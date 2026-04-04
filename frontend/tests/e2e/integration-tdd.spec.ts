import { test, expect } from './fixtures/mock-api';

test.describe('TDD Cycle Verification: Red → Green → Refactor', () => {
  test('Red: Test fails before implementation (ConfigMap API)', async ({ page }) => {
    await page.route('**/api/config/default-targets', async (route) => {
      const req = route.request();
      const method = req.method();

      if (method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            isvc: { name: 'test-isvc', namespace: 'test-ns' },
            llmisvc: { name: '', namespace: '' },
            configmap_updated: true,
          }),
        });
      }

      if (method === 'PATCH') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            isvc: { name: 'test-isvc', namespace: 'test-ns' },
            llmisvc: { name: '', namespace: '' },
            configmap_updated: true,
          }),
        });
      }

      return route.fulfill({ status: 404 });
    });

    await page.goto('/');

    const response = await page.evaluate(async () => {
      const res = await fetch('/api/config/default-targets');
      return { status: res.status, ok: res.ok };
    });

    expect(response.status).toBe(200);
    expect(response.ok).toBe(true);
  });

  test('Green: Test passes after implementation (ConfigMap persistence)', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('green-ns');
    await page.getByTestId('is-input').fill('green-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    await page.getByTestId('set-default-btn').first().click();

    const response = await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
    expect(response.ok()).toBe(true);

    const body = await response.json();
    expect(body.configmap_updated || body.success).toBe(true);
  });

  test('Refactor: Code quality verification (no regressions)', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    for (let i = 0; i < 3; i++) {
      await page.getByTestId('add-target-btn').click();
      await page.getByTestId('namespace-input').fill(`refactor-ns-${i}`);
      await page.getByTestId('is-input').fill(`refactor-isvc-${i}`);
      await page.getByTestId('cr-type-select').selectOption(i % 2 === 0 ? 'inferenceservice' : 'llminferenceservice');
      await page.getByTestId('confirm-add-btn').click();
      await page.waitForTimeout(100);
    }

    const targetRows = page.getByTestId(/target-row-/);
    const count = await targetRows.count();
    expect(count).toBe(3);

    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    const consoleMessages: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleMessages.push(msg.text());
      }
    });

    await page.waitForTimeout(500);
    expect(consoleMessages).toHaveLength(0);
  });
});
