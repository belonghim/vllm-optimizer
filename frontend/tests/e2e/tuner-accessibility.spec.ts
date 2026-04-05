import { test, expect } from './fixtures/mock-api';
import { setupVllmConfigMock } from './fixtures/test-helpers';

test.describe('TunerParamInputs Accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await setupVllmConfigMock(page, {
      model_name: 'test-model',
      max_num_seqs: '128',
      gpu_memory_utilization: '0.85',
      max_model_len: '4096',
      max_num_batched_tokens: '1024',
      block_size: '16',
      swap_space: '2',
    });

    await page.goto('/');
    await page.getByRole('tab', { name: 'Auto Tuner' }).click();
    await page.waitForSelector('[data-testid="tuner-target-selector"]', { timeout: 10000 });
  });

  test('max_num_seqs inputs are accessible via getByLabel', async ({ page }) => {
    const minInput = page.getByLabel('max_num_seqs min');
    const maxInput = page.getByLabel('max_num_seqs max');
    await expect(minInput).toBeVisible();
    await expect(maxInput).toBeVisible();
  });

  test('gpu_memory_utilization inputs are accessible via getByLabel', async ({ page }) => {
    const minInput = page.getByLabel('gpu_memory_utilization min');
    const maxInput = page.getByLabel('gpu_memory_utilization max');
    await expect(minInput).toBeVisible();
    await expect(maxInput).toBeVisible();
  });

  test('max_model_len inputs are accessible via getByLabel', async ({ page }) => {
    const minInput = page.getByLabel('max_model_len min');
    const maxInput = page.getByLabel('max_model_len max');
    await expect(minInput).toBeVisible();
    await expect(maxInput).toBeVisible();
  });

  test('max_num_batched_tokens inputs are accessible via getByLabel', async ({ page }) => {
    const minInput = page.getByLabel('max_num_batched_tokens min');
    const maxInput = page.getByLabel('max_num_batched_tokens max');
    await expect(minInput).toBeVisible();
    await expect(maxInput).toBeVisible();
  });

  test('swap_space inputs are accessible via getByLabel', async ({ page }) => {
    const minInput = page.getByLabel('swap_space min');
    const maxInput = page.getByLabel('swap_space max');
    await expect(minInput).toBeVisible();
    await expect(maxInput).toBeVisible();
  });

  test('block_size checkboxes are accessible via label association', async ({ page }) => {
    const checkbox8 = page.locator('input[id="tuner-block-size-8"]');
    const checkbox16 = page.locator('input[id="tuner-block-size-16"]');
    const checkbox32 = page.locator('input[id="tuner-block-size-32"]');
    await expect(checkbox8).toBeVisible();
    await expect(checkbox16).toBeVisible();
    await expect(checkbox32).toBeVisible();

    const label8 = page.locator('label[for="tuner-block-size-8"]');
    await expect(label8).toBeVisible();
  });

  test('include swap space checkbox is accessible via label association', async ({ page }) => {
    const checkbox = page.locator('input[id="tuner-include-swap-space"]');
    await expect(checkbox).toBeVisible();

    const label = page.locator('label[for="tuner-include-swap-space"]');
    await expect(label).toBeVisible();
  });
});
