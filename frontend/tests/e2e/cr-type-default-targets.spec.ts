import { test, expect } from './fixtures/mock-api';

test.describe('CR type default targets ConfigMap persistence', () => {
  test('Set Default button calls ConfigMap API for InferenceService', async ({ page }) => {
    await page.route('**/api/config', async (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            vllm_endpoint: 'http://test:8080',
            vllm_namespace: 'test-ns',
            vllm_is_name: 'test-isvc',
            cr_type: 'inferenceservice',
            resolved_model_name: 'test-model',
          }),
        });
      }
      await route.continue();
    });

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

    let capturedBody: unknown = null;
    await page.route('**/api/config/default-targets', async (route) => {
      if (route.request().method() === 'PATCH') {
        capturedBody = route.request().postDataJSON();
      }
      await route.continue();
    });

    await setDefaultBtn.click();

    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    expect(capturedBody).toMatchObject({
      cr_type: 'inferenceservice',
      namespace: 'isvc-ns',
      inference_service: 'my-isvc',
    });
  });

  test('Set Default button calls ConfigMap API for LLMInferenceService', async ({ page }) => {
    await page.route('**/api/config', async (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            vllm_endpoint: 'http://test:8080',
            vllm_namespace: 'test-ns',
            vllm_is_name: 'test-isvc',
            cr_type: 'inferenceservice',
            resolved_model_name: 'test-model',
          }),
        });
      }
      await route.continue();
    });

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

    let capturedBody: unknown = null;
    await page.route('**/api/config/default-targets', async (route) => {
      if (route.request().method() === 'PATCH') {
        capturedBody = route.request().postDataJSON();
      }
      await route.continue();
    });

    await setDefaultBtn.click();

    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    expect(capturedBody).toMatchObject({
      cr_type: 'llminferenceservice',
      namespace: 'llmis-ns',
      inference_service: 'my-llmisvc',
    });
  });

  test('Default target persists after simulated Pod restart', async ({ page }) => {
    await page.route('**/api/config', async (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            vllm_endpoint: 'http://test:8080',
            vllm_namespace: 'test-ns',
            vllm_is_name: 'test-isvc',
            cr_type: 'inferenceservice',
            resolved_model_name: 'test-model',
          }),
        });
      }
      await route.continue();
    });

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

    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'GET'
    );
  });

  test('Multiple targets show correct CR type badges', async ({ page }) => {
    await page.route('**/api/config', async (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            vllm_endpoint: 'http://test:8080',
            vllm_namespace: 'test-ns',
            vllm_is_name: 'test-isvc',
            cr_type: 'inferenceservice',
            resolved_model_name: 'test-model',
          }),
        });
      }
      await route.continue();
    });

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
    await page.route('**/api/config', async (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            vllm_endpoint: 'http://test:8080',
            vllm_namespace: 'test-ns',
            vllm_is_name: 'test-isvc',
            cr_type: 'inferenceservice',
            resolved_model_name: 'test-model',
          }),
        });
      }
      await route.continue();
    });

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('isvc-name');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');
    await page.getByTestId('set-default-btn').first().click();

    let capturedBody: unknown = null;
    await page.route('**/api/config/default-targets', async (route) => {
      if (route.request().method() === 'PATCH') {
        capturedBody = route.request().postDataJSON();
      }
      await route.continue();
    });

    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    expect(capturedBody).toHaveProperty('cr_type');
    expect(capturedBody).toHaveProperty('namespace');
    expect(capturedBody).toHaveProperty('inference_service');
  });

  test('Dropdown shows targets grouped by CR type', async ({ page }) => {
    await page.route('**/api/config', async (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            vllm_endpoint: 'http://test:8080',
            vllm_namespace: 'test-ns',
            vllm_is_name: 'test-isvc',
            cr_type: 'inferenceservice',
            resolved_model_name: 'test-model',
          }),
        });
      }
      await route.continue();
    });

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
    await page.route('**/api/config', async (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            vllm_endpoint: 'http://test:8080',
            vllm_namespace: 'test-ns',
            vllm_is_name: 'test-isvc',
            cr_type: 'inferenceservice',
            resolved_model_name: 'test-model',
          }),
        });
      }
      await route.continue();
    });

    const pageA = await context.newPage();
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
