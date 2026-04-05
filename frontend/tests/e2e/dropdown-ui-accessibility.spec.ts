import { test, expect } from './fixtures/mock-api';
import { setupComprehensiveMock } from './fixtures/test-helpers';

const ISVC_TARGET_1 = { namespace: 'vllm-lab-dev', inferenceService: 'llm-ov', crType: 'inferenceservice', isDefault: true };
const ISVC_TARGET_2 = { namespace: 'vllm-lab-prod', inferenceService: 'llm-prod', crType: 'inferenceservice', isDefault: false };

test.describe('Dropdown UI Accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await setupComprehensiveMock(page, {
      targets: [ISVC_TARGET_1, ISVC_TARGET_2],
    });

    await page.goto('/');
    await page.getByRole('tab', { name: 'Auto Tuner' }).click();
    await page.waitForSelector('[data-testid="tuner-target-selector"]', { timeout: 10000 });
  });

  test('TargetSelector has correct ARIA attributes', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await expect(triggerBtn).toHaveAttribute('aria-haspopup', 'listbox');
    await expect(triggerBtn).toHaveAttribute('aria-expanded', 'false');

    await triggerBtn.click();
    await expect(triggerBtn).toHaveAttribute('aria-expanded', 'true');

    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    await expect(dropdown).toHaveAttribute('role', 'listbox');

    const options = page.locator('.target-selector-option');
    await expect(options.first()).toHaveAttribute('role', 'option');
  });

  test('TargetSelector options have aria-selected attribute', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.click();

    const firstOption = page.locator('.target-selector-option').first();
    await expect(firstOption).toHaveAttribute('aria-selected');
  });

  test('TargetSelector options are keyboard focusable', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.focus();
    await triggerBtn.click();

    const options = page.locator('.target-selector-option');
    await expect(options.first()).toHaveAttribute('tabindex', '0');
  });
});
