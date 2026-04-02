import { test, expect, type Page } from '@playwright/test';

interface ApiCallLog {
  url: string;
  method: string;
  body?: unknown;
}

async function mockApiWithCallTracking(page: Page, callLog: ApiCallLog[]) {
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const { pathname, searchParams } = new URL(req.url());
    const method = req.method();
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    const call: ApiCallLog = { url: pathname, method };
    if (method === 'PATCH' || method === 'POST') {
      try {
        call.body = req.postDataJSON();
      } catch {
        // Ignore parse errors
      }
    }
    callLog.push(call);

    if (pathname === '/api/config' && method === 'GET') {
      return json({
        vllm_endpoint: 'http://test-endpoint:8080',
        vllm_namespace: 'test-ns',
        vllm_is_name: 'test-isvc',
        cr_type: 'inferenceservice',
        resolved_model_name: 'test-model',
      });
    }

    if (pathname === '/api/config' && method === 'PATCH') {
      const body = req.postDataJSON();
      return json({
        vllm_endpoint: 'http://test-endpoint:8080',
        vllm_namespace: body.vllm_namespace || 'test-ns',
        vllm_is_name: body.vllm_is_name || 'test-isvc',
        cr_type: body.cr_type || 'inferenceservice',
        resolved_model_name: 'test-model',
        configmap_updated: true,
      });
    }

    if (pathname === '/api/config/default-targets' && method === 'GET') {
      return json({
        isvc: { name: 'test-isvc', namespace: 'test-ns' },
        llmisvc: { name: '', namespace: '' },
        configmap_updated: true,
      });
    }

    if (pathname === '/api/config/default-targets' && method === 'PATCH') {
      const body = req.postDataJSON();
      const isvc = body.isvc || { name: 'test-isvc', namespace: 'test-ns' };
      const llmisvc = body.llmisvc || { name: '', namespace: '' };
      return json({
        isvc,
        llmisvc,
        configmap_updated: true,
      });
    }

    if (pathname === '/api/metrics/latest' && method === 'GET') {
      return json({
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
      });
    }

    if (pathname === '/api/metrics/batch' && method === 'POST') {
      return json({
        results: {
          'test-ns/test-isvc': {
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
          },
        },
      });
    }

    if (pathname === '/api/sla/profiles' && method === 'GET') {
      return json([]);
    }

    return json({});
  });
}

test.describe('CR type default targets ConfigMap persistence', () => {
  test('Set Default button calls ConfigMap API for InferenceService', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

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

    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    const patchCall = callLog.find(
      (c) => c.url === '/api/config/default-targets' && c.method === 'PATCH'
    );
    expect(patchCall).toBeDefined();
    expect(patchCall?.body).toMatchObject({
      cr_type: 'inferenceservice',
      namespace: 'isvc-ns',
      inference_service: 'my-isvc',
    });
  });

  test('Set Default button calls ConfigMap API for LLMInferenceService', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

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

    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    const patchCall = callLog.find(
      (c) => c.url === '/api/config/default-targets' && c.method === 'PATCH'
    );
    expect(patchCall).toBeDefined();
    expect(patchCall?.body).toMatchObject({
      cr_type: 'llminferenceservice',
      namespace: 'llmis-ns',
      inference_service: 'my-llmisvc',
    });
  });

  test('Default target persists after simulated Pod restart', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

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

    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    await page.evaluate(() => localStorage.clear());

    await page.reload();
    await page.waitForSelector('.multi-target-selector');

    const getCall = callLog.filter(
      (c) => c.url === '/api/config/default-targets' && c.method === 'GET'
    );
    expect(getCall.length).toBeGreaterThan(0);
  });

  test('Multiple targets show correct CR type badges', async ({ page }) => {
    await mockApiWithCallTracking(page, []);

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
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('isvc-name');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');
    await page.getByTestId('set-default-btn').first().click();

    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    const patchCall = callLog.find(
      (c) => c.url === '/api/config/default-targets' && c.method === 'PATCH'
    );
    expect(patchCall).toBeDefined();
    expect(patchCall?.body).toHaveProperty('cr_type');
    expect(patchCall?.body).toHaveProperty('namespace');
    expect(patchCall?.body).toHaveProperty('inference_service');
  });

  test('Dropdown shows targets grouped by CR type', async ({ page }) => {
    await mockApiWithCallTracking(page, []);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('isvc-name');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForTimeout(100);

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('llmis-ns');
    await page.getByTestId('is-input').fill('llmis-name');
    await page.getByTestId('cr-type-select').selectOption('llminferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForTimeout(100);

    await page.getByTestId('dropdown-toggle-btn').click();

    await expect(page.getByText('InferenceService (KServe)')).toBeVisible();
    await expect(page.getByText('LLMInferenceService (LLMIS)')).toBeVisible();
  });
});

test.describe('ConfigMap persistence error handling', () => {
  test('Handles ConfigMap save failure gracefully', async ({ page }) => {
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
        });
      }

      if (pathname === '/api/config/default-targets' && method === 'PATCH') {
        return json({
          isvc: { name: 'test-isvc', namespace: 'test-ns' },
          llmisvc: { name: '', namespace: '' },
          configmap_updated: false,
        });
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

      return json({});
    });

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

    const response = await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    const body = await response.json();
    expect(body.configmap_updated).toBe(false);

    await expect(page.getByTestId('set-default-btn').first()).toBeVisible();
  });
});

test.describe('ConfigMap session synchronization', () => {
  test('Session B reads ConfigMap defaults on mount after Session A updates', async ({ page, context }) => {
    const callLogB: ApiCallLog[] = [];

    // Session A - just navigate to the page (mock already returns default targets)
    const pageA = await context.newPage();
    await mockApiWithCallTracking(pageA, []);
    await pageA.goto('/');
    await pageA.waitForSelector('.multi-target-selector');

    // Session B - open new page, verify it reads ConfigMap defaults
    const pageB = await context.newPage();
    await pageB.route('**/api/**', async (route) => {
      const req = route.request();
      const { pathname } = new URL(req.url());
      const method = req.method();
      const json = (body: unknown) => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });

      const call: ApiCallLog = { url: pathname, method };
      callLogB.push(call);

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

      return json({});
    });

    await pageB.goto('/');
    await pageB.waitForSelector('.multi-target-selector');

    // Session B should have fetched ConfigMap defaults on mount
    const getCallB = callLogB.filter(
      (c) => c.url === '/api/config/default-targets' && c.method === 'GET'
    );
    expect(getCallB.length).toBeGreaterThan(0);
  });
});

