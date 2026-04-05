import { test, expect } from './fixtures/mock-api';

const ISVC_TARGET_1 = { namespace: 'vllm-lab-dev', inferenceService: 'llm-ov', crType: 'inferenceservice', isDefault: true };
const ISVC_TARGET_2 = { namespace: 'vllm-lab-prod', inferenceService: 'llm-prod', crType: 'inferenceservice', isDefault: false };
const LLMIS_TARGET_1 = { namespace: 'llm-d-demo', inferenceService: 'small-llm-d', crType: 'llminferenceservice', isDefault: false };

test.describe('MultiTargetSelector Direct Display', () => {
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

      const targets = [ISVC_TARGET_1];

      if (pathname === '/api/config' && method === 'GET') {
        return json({
          vllm_endpoint: 'http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080',
          vllm_namespace: 'vllm-lab-dev',
          vllm_is_name: 'llm-ov',
          cr_type: 'inferenceservice',
          resolved_model_name: 'test-model',
        });
      }

      if (pathname === '/api/config' && method === 'PATCH') {
        return json({ success: true });
      }

      if (pathname === '/api/config/default-targets' && method === 'GET') {
        return json({
          isvc: { name: 'llm-ov', namespace: 'vllm-lab-dev' },
          llmisvc: { name: '', namespace: '' },
          configmap_updated: false,
        });
      }

      if (pathname === '/api/metrics/latest' && method === 'GET') {
        return json({
          status: 'ready',
          data: { tps: 100, rps: 10, kv_cache: 50, running: 5, waiting: 2, gpu_util: 60, pods: 1, pods_ready: 1 },
          hasMonitoringLabel: true,
        });
      }

      if (pathname === '/api/sla/profiles' && method === 'GET') {
        return json([]);
      }

      if (pathname === '/api/metrics/batch' && method === 'POST') {
        const results: Record<string, unknown> = {};
        for (const target of targets) {
          const crType = target.crType || 'inferenceservice';
          const key = `${target.namespace}/${target.inferenceService}/${crType}`;
          results[key] = {
            status: 'ready',
            data: {
              tps: 100,
              rps: 10,
              kv_cache: 50,
              running: 5,
              waiting: 2,
              gpu_util: 60,
              pods: 1,
              pods_ready: 1,
            },
            hasMonitoringLabel: true,
            history: [],
          };
        }
        return json({ results });
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

    await page.goto('/');
    await page.getByRole('tab', { name: 'Monitoring' }).click();
    await page.waitForSelector('.multi-target-selector', { timeout: 10000 });
  });

  test('displays target table directly without dropdown', async ({ page }) => {
    const table = page.locator('.monitor-table');
    await expect(table).toBeVisible();
  });

  test('displays default marker for default target', async ({ page }) => {
    const defaultRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(defaultRow).toBeVisible();
    await expect(defaultRow.locator('.multi-target-default-star')).toContainText('★');
  });

  test('displays namespace under target name', async ({ page }) => {
    const targetRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(targetRow).toBeVisible();
    await expect(targetRow.locator('.target-ns')).toContainText(ISVC_TARGET_1.namespace);
  });

  test('displays add button', async ({ page }) => {
    const addBtn = page.locator('[data-testid="add-target-btn"]');
    await expect(addBtn).toBeVisible();
  });
});

test.describe('MultiTargetSelector LLMIS Metrics Display', () => {
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

      const targets = [ISVC_TARGET_1, LLMIS_TARGET_1];

      if (pathname === '/api/config' && method === 'GET') {
        return json({
          vllm_endpoint: 'http://llm-ov-predictor.vllm-lab-dev.svc.cluster.local:8080',
          vllm_namespace: 'vllm-lab-dev',
          vllm_is_name: 'llm-ov',
          cr_type: 'inferenceservice',
          resolved_model_name: 'test-model',
        });
      }

      if (pathname === '/api/config' && method === 'PATCH') {
        return json({ success: true });
      }

      if (pathname === '/api/config/default-targets' && method === 'GET') {
        return json({
          isvc: { name: 'llm-ov', namespace: 'vllm-lab-dev' },
          llmisvc: { name: 'small-llm-d', namespace: 'llm-d-demo' },
          configmap_updated: false,
        });
      }

      if (pathname === '/api/metrics/latest' && method === 'GET') {
        return json({
          status: 'ready',
          data: { tps: 100, rps: 10, kv_cache: 50, running: 5, waiting: 2, gpu_util: 60, pods: 1, pods_ready: 1 },
          hasMonitoringLabel: true,
        });
      }

      if (pathname === '/api/sla/profiles' && method === 'GET') {
        return json([]);
      }

      if (pathname === '/api/metrics/batch' && method === 'POST') {
        const results: Record<string, unknown> = {};
        for (const target of targets) {
          const crType = target.crType || 'inferenceservice';
          const key = `${target.namespace}/${target.inferenceService}/${crType}`;
          results[key] = {
            status: 'ready',
            data: {
              tps: 100,
              rps: 10,
              kv_cache: 50,
              running: 5,
              waiting: 2,
              gpu_util: 60,
              pods: 1,
              pods_ready: 1,
            },
            hasMonitoringLabel: true,
            history: [],
          };
        }
        return json({ results });
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

    await page.goto('/');
    await page.getByRole('tab', { name: 'Monitoring' }).click();
    await page.waitForSelector('.multi-target-selector', { timeout: 10000 });
  });

  test('displays LLMIS badge for llminferenceservice targets', async ({ page }) => {
    const llmisBadge = page.locator('[data-testid="llmis-badge"]');
    await expect(llmisBadge).toBeVisible();
    await expect(llmisBadge).toContainText('LLMIS');
  });

  test('renders metrics data for LLMIS target', async ({ page }) => {
    const targetRow = page.locator('[data-testid^="target-row-"]').last();
    await expect(targetRow).toBeVisible();
    expect(await targetRow.locator('td').nth(2).textContent()).toBe('100');
  });

  test('displays both ISVC and LLMIS targets in table', async ({ page }) => {
    const rows = page.locator('[data-testid^="target-row-"]');
    await expect(rows).toHaveCount(3);

    const badges = page.locator('.tag');
    await expect(badges.first()).toBeVisible();
    await expect(badges.last()).toBeVisible();
    
    const isvcBadge = page.locator('[data-testid="isvc-badge"]');
    const llmisBadge = page.locator('[data-testid="llmis-badge"]');
    
    await expect(isvcBadge.or(llmisBadge).first()).toBeVisible();
  });

  test('sends correct cr_type in batch metrics request', async ({ page }) => {
    const batchCallPromise = page.waitForResponse(async (response) => {
      if (!response.url().includes('/api/metrics/batch')) return false;
      const request = response.request();
      if (request.method() !== 'POST') return false;
      try {
        const postData = request.postDataJSON();
        return postData.targets?.some((t: { cr_type?: string }) => t.cr_type === 'llminferenceservice');
      } catch {
        return false;
      }
    });

    await page.getByRole('tab', { name: 'Monitoring' }).click();
    await page.waitForSelector('.multi-target-selector', { timeout: 10000 });

    const response = await batchCallPromise;
    const postData = response.request().postDataJSON();

    expect(postData.targets.some((t: { cr_type?: string }) => t.cr_type === 'inferenceservice')).toBe(true);
  });
});
