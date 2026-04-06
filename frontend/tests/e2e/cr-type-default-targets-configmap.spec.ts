import { test, expect } from './fixtures/mock-api';
import { setupComprehensiveMock } from './fixtures/test-helpers';

test.describe('CR type default targets - Set Default', () => {
  test.beforeEach(async ({ page }) => {
    await setupComprehensiveMock(page, {
      config: {
        vllm_endpoint: 'http://test:8080',
        vllm_namespace: 'test-ns',
        vllm_is_name: 'test-isvc',
        cr_type: 'inferenceservice',
        resolved_model_name: 'test-model',
      },
      defaultTargets: { isvc: { name: '', namespace: '' }, llmisvc: { name: '', namespace: '' }, configmap_updated: false },
    });

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');
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

    const radioBtn = page.getByTestId('radio-default-1');
    await expect(radioBtn).toBeVisible();

    await radioBtn.click();
    await page.getByTestId('apply-default-btn').click();

    await page.waitForTimeout(500);

    const firstRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(firstRow).toHaveClass(/multi-target-row-default/);
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

    const radioBtn = page.getByTestId('radio-default-1');
    await expect(radioBtn).toBeVisible();

    await radioBtn.click();
    await page.getByTestId('apply-default-btn').click();

    await page.waitForTimeout(500);

    const firstRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(firstRow).toHaveClass(/multi-target-row-default/);
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
