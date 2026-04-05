import { test, expect } from './fixtures/mock-api';

test.describe('CR type default targets - UI', () => {
  test.beforeEach(async ({ page }) => {
    await page.unrouteAll({ behavior: 'ignoreErrors' });
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
          vllm_endpoint: 'http://test:8080',
          vllm_namespace: 'test-ns',
          vllm_is_name: 'test-isvc',
          cr_type: 'inferenceservice',
          resolved_model_name: 'test-model',
        });
      }

      if (pathname === '/api/config' && method === 'PATCH') {
        return json({ success: true });
      }

      if (pathname === '/api/config/default-targets' && method === 'GET') {
        return json({ isvc: { name: '', namespace: '' }, llmisvc: { name: '', namespace: '' }, configmap_updated: false });
      }

      if (pathname === '/api/config/default-targets' && method === 'PATCH') {
        return json({ success: true, configmap_updated: true });
      }

      if (pathname === '/api/metrics/latest' && method === 'GET') {
        return json({ status: 'ready', data: { tps: 100 }, hasMonitoringLabel: true });
      }

      if (pathname === '/api/metrics/batch' && method === 'POST') {
        return json({ results: {} });
      }

      if (pathname === '/api/sla/profiles' && method === 'GET') {
        return json([]);
      }

      if (pathname === '/api/tuner/all' && method === 'GET') {
        return json({ status: { running: false, trials_completed: 0 }, trials: [], importance: {} });
      }

      if (pathname === '/api/tuner/status' && method === 'GET') {
        return json({ running: false, trials_completed: 0 });
      }

      if (pathname === '/api/tuner/trials' && method === 'GET') {
        return json([]);
      }

      if (pathname === '/api/tuner/importance' && method === 'GET') {
        return json({});
      }

      if (pathname === '/api/vllm-config' && method === 'GET') {
        return json({ success: true, data: { model_name: 'test-model', max_num_seqs: '128' } });
      }

      if (pathname === '/api/status/interrupted' && method === 'GET') {
        return json({ interrupted_runs: [] });
      }

      return json({});
    });
  });

  test('Multiple targets show correct CR type badges', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('ns1');
    await page.getByTestId('is-input').fill('isvc-target');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForTimeout(100);

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('ns2');
    await page.getByTestId('is-input').fill('llmisvc-target');
    await page.getByTestId('cr-type-select').selectOption('llminferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForTimeout(100);

    const llmisBadge = page.getByTestId('llmis-badge');
    await expect(llmisBadge).toBeVisible();
    expect(await llmisBadge.textContent()).toContain('LLMIS');
  });

  test('ConfigMap API returns correct structure for both CR types', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('isvc-name');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForTimeout(100);

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns-2');
    await page.getByTestId('is-input').fill('isvc-name-2');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');
    await page.getByTestId('set-default-btn').first().click();

    await page.waitForTimeout(500);

    const firstRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(firstRow.locator('.multi-target-default-star')).toBeVisible();
  });

  test('Dropdown shows targets grouped by CR type', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    const initialRows = page.locator('[data-testid^="target-row-"]');
    const initialCount = await initialRows.count();

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('isvc-name');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForTimeout(300);

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('llmis-ns');
    await page.getByTestId('is-input').fill('llmis-name');
    await page.getByTestId('cr-type-select').selectOption('llminferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForTimeout(300);

    const rows = page.locator('[data-testid^="target-row-"]');
    expect(await rows.count()).toBeGreaterThan(initialCount);
  });
});
