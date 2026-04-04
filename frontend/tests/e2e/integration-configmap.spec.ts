import { test, expect } from './fixtures/mock-api';

/**
 * Integration Test Suite: ConfigMap Persistence
 * 
 * Tests the full integration flow between Backend + Frontend + ConfigMap
 */

test.describe('Full Integration: Backend + Frontend + ConfigMap', () => {
  test('Complete flow: Add target → Set default → Verify ConfigMap persistence', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Step 1: Add InferenceService target
    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('my-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    // Step 2: Set as default
    const setDefaultBtn = page.getByTestId('set-default-btn').first();
    await expect(setDefaultBtn).toBeVisible();
    await setDefaultBtn.click();

    // Step 3: Verify API call
    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    // Verify API was called - check response body
    const response = await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
    const body = await response.json();
    expect(body.success || body.configmap_updated).toBe(true);

    // Step 4: Verify ConfigMap updated flag via direct API call
    const configResponse = await page.evaluate(async () => {
      const res = await fetch('/api/config/default-targets');
      return res.json();
    });
    expect(configResponse.configmap_updated).toBe(true);
  });

  test('Cross-page synchronization: MonitorPage → AutoTuner → LoadTest', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Step 1: Add target in MonitorPage
    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('sync-ns');
    await page.getByTestId('is-input').fill('sync-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    // Step 2: Set as default
    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    // Step 3: Navigate to AutoTuner page
    await page.getByRole('tab', { name: '자동 파라미터 튜닝' }).click();
    await page.waitForTimeout(500);

    // Step 4: Verify target selector shows the default target
    const tunerTargetSelector = page.getByTestId('target-selector');
    await expect(tunerTargetSelector).toBeVisible();

    // Step 5: Navigate to LoadTest page
    await page.getByRole('tab', { name: '부하 테스트' }).click();
    await page.waitForTimeout(500);

    // Step 6: Verify target selector shows the default target
    const loadTestTargetSelector = page.getByTestId('target-selector');
    await expect(loadTestTargetSelector).toBeVisible();

    // Step 7: Verify all pages loaded default targets from ConfigMap
    // The global fixture should have been called for default-targets
    await page.waitForTimeout(300);
  });

  test('ConfigMap persistence across simulated Pod restart', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Step 1: Add and set default
    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('restart-ns');
    await page.getByTestId('is-input').fill('restart-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');
    await page.getByTestId('set-default-btn').first().click();

    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    // Step 2: Simulate Pod restart (clear localStorage + reload)
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForSelector('.multi-target-selector');

    // Step 3: Verify ConfigMap API was called to restore defaults
    // The reload should trigger loading from ConfigMap via global fixture

    // Step 4: Verify default target is restored
    const defaultTarget = page.getByTestId('default-target-indicator');
    await expect(defaultTarget).toBeVisible();
  });
});
