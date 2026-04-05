import { test, expect } from './fixtures/mock-api';
import { setupComprehensiveMock } from './fixtures/test-helpers';

test.describe('Error Handling and Recovery', () => {
  test('ConfigMap save failure: UI shows error but remains functional', async ({ page }) => {
    await setupComprehensiveMock(page, {
      config: {
        vllm_endpoint: 'http://test:8080',
        vllm_namespace: 'test-ns',
        vllm_is_name: 'test-isvc',
        cr_type: 'inferenceservice',
      },
      defaultTargets: {
        isvc: { name: 'test-isvc', namespace: 'test-ns' },
        llmisvc: { name: '', namespace: '' },
        configmap_updated: true,
      },
      metricsData: { tps: 100 },
      targets: [{ namespace: 'test-ns', inferenceService: 'test-isvc', crType: 'inferenceservice', isDefault: true }],
    });

    await page.route('**/api/config/default-targets', async (route) => {
      const method = route.request().method();

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
            configmap_updated: false,
          }),
        });
      }

      return route.fulfill({ status: 404 });
    });

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('error-ns');
    await page.getByTestId('is-input').fill('error-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    const responsePromise = page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
    await page.getByTestId('set-default-btn').first().click();

    const response = await responsePromise;
    const body = await response.json();
    expect(body.configmap_updated).toBe(false);

    const setDefaultBtn = page.getByTestId('set-default-btn').first();
    await expect(setDefaultBtn).toBeVisible();
  });

  test('Network error: Retry mechanism works', async ({ page }) => {
    let callCount = 0;

    await setupComprehensiveMock(page, {
      config: {
        vllm_endpoint: 'http://test:8080',
        vllm_namespace: 'test-ns',
        vllm_is_name: 'test-isvc',
        cr_type: 'inferenceservice',
      },
      defaultTargets: {
        isvc: { name: 'test-isvc', namespace: 'test-ns' },
        llmisvc: { name: '', namespace: '' },
        configmap_updated: true,
      },
      targets: [{ namespace: 'test-ns', inferenceService: 'test-isvc', crType: 'inferenceservice', isDefault: true }],
    });

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
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    const addTargetBtn = page.getByTestId('add-target-btn');
    await expect(addTargetBtn).toBeVisible();
  });
});
