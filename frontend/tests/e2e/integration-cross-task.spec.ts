import { test, expect } from './fixtures/mock-api';

test.describe('Cross-Task Integration: MonitorPage + AutoTuner + LoadTest', () => {
  test('MonitorPage default affects AutoTuner target selector', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('monitor-ns');
    await page.getByTestId('is-input').fill('monitor-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    await page.getByRole('tab', { name: '자동 파라미터 튜닝' }).click();
    await page.waitForTimeout(500);

    const tunerTargetSelector = page.getByTestId('target-selector');
    await expect(tunerTargetSelector).toBeVisible();
  });

  test('MonitorPage default affects LoadTest target selector', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('loadtest-ns');
    await page.getByTestId('is-input').fill('loadtest-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    await page.getByRole('tab', { name: '부하 테스트' }).click();
    await page.waitForTimeout(500);

    const loadTestTargetSelector = page.getByTestId('target-selector');
    await expect(loadTestTargetSelector).toBeVisible();
  });

  test('AutoTuner and LoadTest use same target from ConfigMap', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('shared-ns');
    await page.getByTestId('is-input').fill('shared-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    await page.getByRole('tab', { name: '자동 파라미터 튜닝' }).click();
    await page.waitForTimeout(500);

    const tunerTargetSelector = page.getByTestId('target-selector');
    await expect(tunerTargetSelector).toBeVisible();

    await page.getByRole('tab', { name: '부하 테스트' }).click();
    await page.waitForTimeout(500);

    const loadTestTargetSelector = page.getByTestId('target-selector');
    await expect(loadTestTargetSelector).toBeVisible();
  });
});
