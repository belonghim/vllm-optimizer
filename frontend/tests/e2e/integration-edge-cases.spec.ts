import { test, expect } from './fixtures/mock-api';

test.describe('Edge Cases: Empty and Deleted Targets', () => {
  test('Empty targets state: UI shows empty state message', async ({ page }) => {
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
          vllm_endpoint: '',
          vllm_namespace: '',
          vllm_is_name: '',
          cr_type: 'inferenceservice',
        });
      }

      if (pathname === '/api/config/default-targets' && method === 'GET') {
        return json({
          isvc: { name: '', namespace: '' },
          llmisvc: { name: '', namespace: '' },
          configmap_updated: true,
        });
      }

      if (pathname === '/api/metrics/latest' && method === 'GET') {
        return json({ status: 'ready', data: {}, hasMonitoringLabel: false });
      }

      if (pathname === '/api/sla/profiles' && method === 'GET') {
        return json([]);
      }

      return json({});
    });

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    const addTargetBtn = page.getByTestId('add-target-btn');
    await expect(addTargetBtn).toBeVisible();

    const targetRows = page.getByTestId(/target-row-/);
    const count = await targetRows.count();
    expect(count).toBe(0);
  });

  test('Deleted target: Default target removed, fallback to empty', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('delete-ns');
    await page.getByTestId('is-input').fill('delete-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    await page.getByTestId('remove-target-btn').first().click();
    await page.waitForTimeout(200);

    const targetRows = page.getByTestId(/target-row-/);
    const count = await targetRows.count();
    expect(count).toBe(0);
  });
});

test.describe('Multiple CR Types', () => {
  test('Switching between isvc and llmisvc', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('isvc-name');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();
    await page.waitForTimeout(100);

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('llmisvc-ns');
    await page.getByTestId('is-input').fill('llmisvc-name');
    await page.getByTestId('cr-type-select').selectOption('llminferenceservice');
    await page.getByTestId('confirm-add-btn').click();
    await page.waitForTimeout(100);

    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    await page.getByTestId('set-default-btn').last().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
  });

  test('Concurrent operations: Rapid add/remove/set-default', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    for (let i = 0; i < 5; i++) {
      await page.getByTestId('add-target-btn').click();
      await page.getByTestId('namespace-input').fill(`rapid-ns-${i}`);
      await page.getByTestId('is-input').fill(`rapid-isvc-${i}`);
      await page.getByTestId('cr-type-select').selectOption('inferenceservice');
      await page.getByTestId('confirm-add-btn').click();
      await page.waitForTimeout(50);
    }

    const targetRows = page.getByTestId(/target-row-/);
    const count = await targetRows.count();
    expect(count).toBe(5);

    for (let i = 0; i < 3; i++) {
      await page.getByTestId('set-default-btn').first().click();
      await page.waitForTimeout(100);
    }

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
