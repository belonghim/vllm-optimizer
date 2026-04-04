import { test, expect } from './fixtures/mock-api';

test.describe('CR type default targets - UI', () => {
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
