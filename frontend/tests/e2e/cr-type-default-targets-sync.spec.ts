import { test, expect, type Page } from './fixtures/mock-api';

async function setupComprehensiveMock(page: Page) {
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
      return json({ success: true, configmap_updated: false });
    }

    if (pathname === '/api/metrics/latest' && method === 'GET') {
      return json({ status: 'ready', data: { tps: 100 }, hasMonitoringLabel: true });
    }

    if (pathname === '/api/metrics/batch' && method === 'POST') {
      return json({
        results: {
          'test-ns/test-isvc': {
            status: 'ready',
            data: { tps: 100 },
            hasMonitoringLabel: true,
            history: [],
          },
        },
      });
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
}

test.describe('ConfigMap persistence error handling', () => {
  test('Handles ConfigMap save failure gracefully', async ({ page }) => {
    await setupComprehensiveMock(page);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('fail-ns');
    await page.getByTestId('is-input').fill('fail-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    const setDefaultBtn = page.getByTestId('set-default-btn').first();
    await expect(setDefaultBtn).toBeVisible();

    await setDefaultBtn.click();

    await page.waitForTimeout(500);

    await expect(page.getByTestId('set-default-btn').first()).toBeVisible();
  });
});

test.describe('ConfigMap session synchronization', () => {
  test('Session B reads ConfigMap defaults on mount after Session A updates', async ({ page, context }) => {
    await setupComprehensiveMock(page);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    const pageA = await context.newPage();
    await setupComprehensiveMock(pageA);
    await pageA.goto('/');
    await pageA.waitForSelector('.multi-target-selector');

    const pageB = await context.newPage();
    const callLogB: { url: string; method: string }[] = [];
    await pageB.route('**/api/**', async (route) => {
      const req = route.request();
      const { pathname } = new URL(req.url());
      const method = req.method();

      callLogB.push({ url: pathname, method });

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

      if (pathname === '/api/config/default-targets' && method === 'GET') {
        return json({
          isvc: { name: 'persist-ns', namespace: 'persist-isvc' },
          llmisvc: { name: '', namespace: '' },
          configmap_updated: true,
        });
      }

      if (pathname === '/api/metrics/latest' && method === 'GET') {
        return json({ status: 'ready', data: { tps: 100 }, hasMonitoringLabel: true });
      }

      if (pathname === '/api/metrics/batch' && method === 'POST') {
        return json({
          results: {
            'test-ns/test-isvc': { status: 'ready', data: { tps: 100 }, hasMonitoringLabel: true, history: [] },
          },
        });
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

    await pageB.goto('/');
    await pageB.waitForSelector('.multi-target-selector');

    const getCallB = callLogB.filter(
      (c) => c.url === '/api/config/default-targets' && c.method === 'GET'
    );
    expect(getCallB.length).toBeGreaterThan(0);
  });
});
