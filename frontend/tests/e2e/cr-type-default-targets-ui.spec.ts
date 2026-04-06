import { test, expect } from './fixtures/mock-api';
import { setupComprehensiveMock } from './fixtures/test-helpers';

test.describe('CR type default targets - UI', () => {
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
      vllmConfig: {
        model_name: 'test-model',
        max_num_seqs: '128',
        gpu_memory_utilization: '0.85',
        max_model_len: '4096',
        max_num_batched_tokens: '1024',
        block_size: '16',
        swap_space: '2',
      },
    });
  });

  test('Multiple targets show correct CR type badges', async ({ page }) => {
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
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('isvc-name');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForTimeout(100);

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns-2');
    await page.getByTestId('is-input').fill('isvc-name-2');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');
    await page.getByTestId('radio-default-1').click();
    await page.getByTestId('apply-default-btn').click();

    await page.waitForTimeout(500);

    const firstRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(firstRow).toHaveClass(/multi-target-row-default/);
  });

  test('Dropdown shows targets grouped by CR type', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    const initialRows = page.locator('[data-testid^="target-row-"]');
    const initialCount = await initialRows.count();

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('isvc-name');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForTimeout(300);

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('llmis-ns');
    await page.getByTestId('is-input').fill('llmis-name');
    await page.getByTestId('cr-type-select').selectOption('llminferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForTimeout(300);

    const rows = page.locator('[data-testid^="target-row-"]');
    expect(await rows.count()).toBeGreaterThan(initialCount);
  });
});
