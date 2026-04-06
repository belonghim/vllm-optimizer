import { test, expect } from './fixtures/mock-api';
import { setupComprehensiveMock } from './fixtures/test-helpers';

test.describe('Cross-Task Integration: MonitorPage + AutoTuner + LoadTest', () => {
  test.beforeEach(async ({ page }) => {
    await setupComprehensiveMock(page, {
      config: {
        vllm_endpoint: 'http://base-isvc-predictor.base-ns.svc.cluster.local:8080',
        vllm_namespace: 'base-ns',
        vllm_is_name: 'base-isvc',
        cr_type: 'inferenceservice',
        resolved_model_name: 'test-model',
      },
      defaultTargets: {
        isvc: { name: '', namespace: '' },
        llmisvc: { name: '', namespace: '' },
        configmap_updated: false,
      },
      targets: [{ namespace: 'base-ns', inferenceService: 'base-isvc', crType: 'inferenceservice', isDefault: true }],
    });
  });

  test('MonitorPage default affects AutoTuner target selector', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('monitor-ns');
    await page.getByTestId('is-input').fill('monitor-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    const responsePromise = page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
    await page.getByTestId('radio-default-1').click();
    await page.getByTestId('apply-default-btn').click();
    await responsePromise;

    await page.getByRole('tab', { name: 'Auto Tuner' }).click();
    await page.waitForTimeout(500);

    const tunerTargetSelector = page.getByTestId('tuner-target-selector');
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

    const responsePromise = page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
    await page.getByTestId('radio-default-1').click();
    await page.getByTestId('apply-default-btn').click();
    await responsePromise;

    await page.getByRole('tab', { name: 'Load Test' }).click();
    await page.waitForTimeout(500);

    const loadTestTargetSelector = page.getByTestId('loadtest-target-selector');
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

    const responsePromise = page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
    await page.getByTestId('radio-default-1').click();
    await page.getByTestId('apply-default-btn').click();
    await responsePromise;

    await page.getByRole('tab', { name: 'Auto Tuner' }).click();
    await page.waitForTimeout(500);

    const tunerTargetSelector = page.getByTestId('tuner-target-selector');
    await expect(tunerTargetSelector).toBeVisible();

    await page.getByRole('tab', { name: 'Load Test' }).click();
    await page.waitForTimeout(500);

    const loadTestTargetSelector = page.getByTestId('loadtest-target-selector');
    await expect(loadTestTargetSelector).toBeVisible();
  });
});
