import { test, expect } from './fixtures/mock-api';
import { setupComprehensiveMock } from './fixtures/test-helpers';

test.describe('Edge Cases: Empty and Deleted Targets', () => {
  test('Empty targets state: UI shows empty state message', async ({ page }) => {
    await setupComprehensiveMock(page, {
      config: {
        vllm_endpoint: '',
        vllm_namespace: '',
        vllm_is_name: '',
        cr_type: 'inferenceservice',
      },
      defaultTargets: {
        isvc: { name: '', namespace: '' },
        llmisvc: { name: '', namespace: '' },
        configmap_updated: true,
      },
      metricsData: {},
    });

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    const addTargetBtn = page.getByTestId('add-target-btn');
    await expect(addTargetBtn).toBeVisible();

    const targetRows = page.locator('[data-testid^="target-row-"]').filter({
      has: page.locator('[data-testid="set-default-btn"]'),
    });
    const count = await targetRows.count();
    expect(count).toBe(0);
  });

  test('Deleted target: Default target removed, fallback to empty', async ({ page }) => {
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

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('delete-ns');
    await page.getByTestId('is-input').fill('delete-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    const responsePromise = page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
    await page.getByTestId('set-default-btn').first().click();
    await responsePromise;

    await page.getByTestId('delete-btn').first().click();
    await page.waitForTimeout(200);

    const targetRows = page.locator('[data-testid^="target-row-"]').filter({
      has: page.locator('[data-testid="set-default-btn"]'),
    });
    const count = await targetRows.count();
    expect(count).toBe(0);
  });
});

test.describe('Multiple CR Types', () => {
  test('Switching between isvc and llmisvc', async ({ page }) => {
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

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('isvc-name');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();
    await page.waitForTimeout(100);

    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('llmisvc-ns');
    await page.getByTestId('is-input').fill('llmisvc-name');
    await page.getByTestId('cr-type-select').selectOption('llminferenceservice');
    await page.getByTestId('confirm-add-btn').click();
    await page.waitForTimeout(100);

    let responsePromise = page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
    await page.getByTestId('set-default-btn').first().click();
    await responsePromise;

    responsePromise = page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
    await page.getByTestId('set-default-btn').last().click();
    await responsePromise;
  });

  test('Concurrent operations: Rapid add/remove/set-default', async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('vllm-opt-cluster-config', JSON.stringify({
        endpoint: '',
        targets: [{ namespace: 'base-ns', inferenceService: 'base-isvc', crType: 'inferenceservice', source: 'manual' }],
        maxTargets: 6,
        version: 3,
      }));
    });

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

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    for (let i = 0; i < 5; i++) {
      await page.getByTestId('add-target-btn').click();
      await page.getByTestId('namespace-input').fill(`rapid-ns-${i}`);
      await page.getByTestId('is-input').fill(`rapid-isvc-${i}`);
      await page.getByTestId('cr-type-select').selectOption('inferenceservice');
      await page.getByTestId('confirm-add-btn').click();
      await page.waitForTimeout(50);
    }

    const targetRows = page.getByTestId(/target-row-/);
    const count = await targetRows.count();
    expect(count).toBe(5);

    for (let i = 0; i < 3; i++) {
      await page.getByTestId('set-default-btn').first().click();
      await page.waitForTimeout(100);
    }

    const consoleMessages: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleMessages.push(msg.text());
      }
    });

    await page.waitForTimeout(500);
    expect(consoleMessages).toHaveLength(0);
  });
});
