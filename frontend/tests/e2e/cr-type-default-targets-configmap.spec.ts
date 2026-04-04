import { test, expect } from './fixtures/mock-api';

test.describe('CR type default targets - Set Default', () => {
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
});
