import { test, expect } from './fixtures/mock-api';
import { setupComprehensiveMock } from './fixtures/test-helpers';

const ISVC_TARGET_1 = { namespace: 'vllm-lab-dev', inferenceService: 'llm-ov', crType: 'inferenceservice', isDefault: true };
const ISVC_TARGET_2 = { namespace: 'vllm-lab-prod', inferenceService: 'llm-prod', crType: 'inferenceservice', isDefault: false };
const LLMIS_TARGET_1 = { namespace: 'llm-d-demo', inferenceService: 'small-llm-d', crType: 'llminferenceservice', isDefault: false };

test.describe('MultiTargetSelector Direct Display', () => {
  test.beforeEach(async ({ page }) => {
    await setupComprehensiveMock(page, {
      targets: [ISVC_TARGET_1],
    });

    await page.goto('/');
    await page.getByRole('tab', { name: 'Monitoring' }).click();
    await page.waitForSelector('.multi-target-selector', { timeout: 10000 });
  });

  test('displays target table directly without dropdown', async ({ page }) => {
    const table = page.locator('.monitor-table');
    await expect(table).toBeVisible();
  });

  test('displays default marker for default target', async ({ page }) => {
    const defaultRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(defaultRow).toBeVisible();
    await expect(defaultRow).toHaveClass(/multi-target-row-default/);
    const radio = defaultRow.locator('[data-testid="radio-default-0"]');
    await expect(radio).toBeChecked();
  });

  test('displays namespace under target name', async ({ page }) => {
    const targetRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(targetRow).toBeVisible();
    await expect(targetRow.locator('.target-ns')).toContainText(ISVC_TARGET_1.namespace);
  });

  test('displays add button', async ({ page }) => {
    const addBtn = page.locator('[data-testid="add-target-btn"]');
    await expect(addBtn).toBeVisible();
  });
});

test.describe('MultiTargetSelector LLMIS Metrics Display', () => {
  test.beforeEach(async ({ page }) => {
    await setupComprehensiveMock(page, {
      targets: [
        { namespace: 'vllm-lab-dev', inferenceService: 'llm-ov', crType: 'inferenceservice', isDefault: true },
        LLMIS_TARGET_1,
      ],
      defaultTargets: {
        isvc: { name: 'llm-ov', namespace: 'vllm-lab-dev' },
        llmisvc: { name: 'small-llm-d', namespace: 'llm-d-demo' },
        configmap_updated: false,
      },
    });

    await page.goto('/');
    await page.getByRole('tab', { name: 'Monitoring' }).click();
    await page.waitForSelector('.multi-target-selector', { timeout: 10000 });
  });

  test('displays LLMIS badge for llminferenceservice targets', async ({ page }) => {
    const llmisBadge = page.locator('[data-testid="llmis-badge"]');
    await expect(llmisBadge).toBeVisible();
    await expect(llmisBadge).toContainText('LLMIS');
  });

  test('renders metrics data for LLMIS target', async ({ page }) => {
    const targetRow = page.locator('[data-testid^="target-row-"]').last();
    await expect(targetRow).toBeVisible();
    expect(await targetRow.locator('td').nth(2).textContent()).toBe('100');
  });

  test('displays both ISVC and LLMIS targets in table', async ({ page }) => {
    const rows = page.locator('[data-testid^="target-row-"]');
    await expect(rows).toHaveCount(3);

    const badges = page.locator('.tag');
    await expect(badges.first()).toBeVisible();
    await expect(badges.last()).toBeVisible();
    
    const isvcBadge = page.locator('[data-testid="isvc-badge"]');
    const llmisBadge = page.locator('[data-testid="llmis-badge"]');
    
    await expect(isvcBadge.or(llmisBadge).first()).toBeVisible();
  });

  test('sends correct cr_type in batch metrics request', async ({ page }) => {
    const batchCallPromise = page.waitForResponse(async (response) => {
      if (!response.url().includes('/api/metrics/batch')) return false;
      const request = response.request();
      if (request.method() !== 'POST') return false;
      try {
        const postData = request.postDataJSON();
        return postData.targets?.some((t: { cr_type?: string }) => t.cr_type === 'llminferenceservice');
      } catch {
        return false;
      }
    });

    await page.getByRole('tab', { name: 'Monitoring' }).click();
    await page.waitForSelector('.multi-target-selector', { timeout: 10000 });

    const response = await batchCallPromise;
    const postData = response.request().postDataJSON();

    expect(postData.targets.some((t: { cr_type?: string }) => t.cr_type === 'inferenceservice')).toBe(true);
  });
});
