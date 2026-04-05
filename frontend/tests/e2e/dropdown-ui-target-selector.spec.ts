import { test, expect } from './fixtures/mock-api';
import { setupComprehensiveMock } from './fixtures/test-helpers';

const ISVC_TARGET_1 = { namespace: 'vllm-lab-dev', inferenceService: 'llm-ov', crType: 'inferenceservice', isDefault: true };
const ISVC_TARGET_2 = { namespace: 'vllm-lab-prod', inferenceService: 'llm-prod', crType: 'inferenceservice', isDefault: false };

test.describe('TargetSelector Dropdown UI', () => {
  test.beforeEach(async ({ page, mockApi: _mockApi }) => {
    await setupComprehensiveMock(page, {
      targets: [ISVC_TARGET_1, ISVC_TARGET_2],
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

    await page.goto('/');
    await page.getByRole('tab', { name: 'Auto Tuner' }).click();
    await page.waitForSelector('[data-testid="tuner-target-selector"]', { timeout: 10000 });
  });

  test('displays dropdown trigger button', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await expect(triggerBtn).toBeVisible();
    await expect(triggerBtn).toHaveAttribute('aria-haspopup', 'listbox');
  });

  test('opens dropdown on click', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.click();

    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    await expect(dropdown).toBeVisible();
    await expect(dropdown).toHaveAttribute('role', 'listbox');
  });

  test('closes dropdown on outside click', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.click();

    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    await expect(dropdown).toBeVisible();

    await page.click('body', { position: { x: 10, y: 10 } });
    await expect(dropdown).not.toBeVisible();
  });

  test('closes dropdown on Escape key', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.click();

    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    await expect(dropdown).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(dropdown).not.toBeVisible();
  });

  test('displays default marker (★) for default target', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.click();

    const defaultOption = page.locator('.target-selector-option').first();
    await expect(defaultOption.locator('.target-selector-option-star')).toContainText('★');
  });

  test('selects option on click', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    
    await triggerBtn.click();
    await expect(dropdown).toBeVisible();
    
    const secondOption = page.locator('.target-selector-option').nth(1);
    await expect(secondOption).toBeVisible();
    await secondOption.click();
    
    await expect(dropdown).not.toBeVisible();
  });

  test('supports keyboard navigation with ArrowDown', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.focus();
    await triggerBtn.click();

    await page.keyboard.press('ArrowDown');

    const firstOption = page.locator('.target-selector-option').first();
    await expect(firstOption).toHaveClass(/highlighted/);
  });

  test('supports keyboard navigation with ArrowUp', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.focus();
    await triggerBtn.click();

    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowUp');

    const firstOption = page.locator('.target-selector-option').first();
    await expect(firstOption).toHaveClass(/highlighted/);
  });

  test('selects option with Enter key', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.focus();
    await triggerBtn.click();

    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');

    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    await expect(dropdown).not.toBeVisible();
  });

  test('displays namespace in parentheses', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    
    await triggerBtn.click();
    
    const options = page.locator('.target-selector-option');
    await expect(options.first()).toContainText(ISVC_TARGET_1.namespace);
  });
});
