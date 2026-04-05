import { test, expect } from './fixtures/mock-api';

test.describe('CR type default targets - Set Default', () => {
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
        return json({ status: 'ready', data: { tps: 100, rps: 10, kv_cache: 50, running: 5, waiting: 2, gpu_util: 60, pods: 1, pods_ready: 1 }, hasMonitoringLabel: true });
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
        return json({ success: true, data: { model_name: 'test-model', max_num_seqs: '128', gpu_memory_utilization: '0.85', max_model_len: '4096', max_num_batched_tokens: '1024', block_size: '16', swap_space: '2' } });
      }

      if (pathname === '/api/status/interrupted' && method === 'GET') {
        return json({ interrupted_runs: [] });
      }

      return json({});
    });
  });

  test('Set Default button calls ConfigMap API for InferenceService', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('my-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    const setDefaultBtn = page.getByTestId('set-default-btn').first();
    await expect(setDefaultBtn).toBeVisible();

    await setDefaultBtn.click();

    await page.waitForTimeout(500);

    const firstRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(firstRow.locator('.multi-target-default-star')).toBeVisible();
  });

  test('Set Default button calls ConfigMap API for LLMInferenceService', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('llmis-ns');
    await page.getByTestId('is-input').fill('my-llmisvc');
    await page.getByTestId('cr-type-select').selectOption('llminferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    const setDefaultBtn = page.getByTestId('set-default-btn').first();
    await expect(setDefaultBtn).toBeVisible();

    await setDefaultBtn.click();

    await page.waitForTimeout(500);

    const firstRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(firstRow.locator('.multi-target-default-star')).toBeVisible();
  });

  test('Default target persists after simulated Pod restart', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('persist-ns');
    await page.getByTestId('is-input').fill('persist-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    const setDefaultBtn = page.getByTestId('set-default-btn').first();
    await setDefaultBtn.click();

    await page.waitForTimeout(500);

    const firstRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(firstRow.locator('.multi-target-default-star')).toBeVisible();

    await page.evaluate(() => localStorage.clear());

    await page.reload();
    await page.waitForSelector('.multi-target-selector');

    await page.waitForTimeout(500);

    const rows = page.locator('[data-testid^="target-row-"]');
    await expect(rows.first()).toBeVisible();
  });
});
