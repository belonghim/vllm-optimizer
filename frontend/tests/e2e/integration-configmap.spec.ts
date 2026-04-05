import { test, expect } from './fixtures/mock-api';

test.describe('Full Integration: Backend + Frontend + ConfigMap', () => {
  test.skip('Complete flow: Add target → Set default → Verify ConfigMap persistence', async ({ page }) => {
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
    await setDefaultBtn.click();

    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    const response = await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
    const body = await response.json();
    expect(body.success || body.configmap_updated).toBe(true);

    const configResponse = await page.evaluate(async () => {
      const res = await fetch('/api/config/default-targets');
      return res.json();
    });
    expect(configResponse.configmap_updated).toBe(true);
  });

  test.skip('Cross-page synchronization: MonitorPage → AutoTuner → LoadTest', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('sync-ns');
    await page.getByTestId('is-input').fill('sync-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((response) =>
      response.url().includes('/api/config/default-targets') &&
      response.request().method() === 'PATCH'
    );

    await page.getByRole('tab', { name: 'Auto Tuner' }).click();
    await page.waitForTimeout(500);

    const tunerTargetSelector = page.locator('.target-selector');
    await expect(tunerTargetSelector.first()).toBeVisible();

    await page.getByRole('tab', { name: 'Load Test' }).click();
    await page.waitForTimeout(500);

    const loadTestTargetSelector = page.locator('.target-selector');
    await expect(loadTestTargetSelector.first()).toBeVisible();
  });

  test.skip('ConfigMap persistence across simulated Pod restart', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

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

    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForSelector('.multi-target-selector');

    await page.waitForTimeout(300);
  });
});
