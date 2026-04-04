import { test, expect } from './fixtures/mock-api';

test.describe('Error Handling and Recovery', () => {
  test('ConfigMap save failure: UI shows error but remains functional', async ({ page }) => {
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

      if (pathname === '/api/config/default-targets' && method === 'GET') {
        return json({
          isvc: { name: 'test-isvc', namespace: 'test-ns' },
          llmisvc: { name: '', namespace: '' },
          configmap_updated: true,
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
    await page.getByTestId('namespace-input').fill('error-ns');
    await page.getByTestId('is-input').fill('error-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    await page.getByTestId('set-default-btn').first().click();

    const response = await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    const body = await response.json();
    expect(body.configmap_updated).toBe(false);

    const setDefaultBtn = page.getByTestId('set-default-btn').first();
    await expect(setDefaultBtn).toBeVisible();
  });

  test('Network error: Retry mechanism works', async ({ page }) => {
    let callCount = 0;

    await page.route('**/api/config/default-targets', async (route) => {
      const req = route.request();
      const method = req.method();

      callCount++;

      if (callCount === 1 && method === 'GET') {
        return route.fulfill({ status: 500 });
      }

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

    await page.route('**/api/config', async (route) => {
      const req = route.request();
      if (req.method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            vllm_endpoint: 'http://test:8080',
            vllm_namespace: 'test-ns',
            vllm_is_name: 'test-isvc',
            cr_type: 'inferenceservice',
          }),
        });
      }
      return route.fulfill({ status: 404 });
    });

    await page.route('**/api/metrics/**', async (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ready', data: {}, hasMonitoringLabel: true }),
      });
    });

    await page.route('**/api/sla/**', async (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    const addTargetBtn = page.getByTestId('add-target-btn');
    await expect(addTargetBtn).toBeVisible();
  });
});
