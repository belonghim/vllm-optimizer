import { test, expect } from './fixtures/mock-api';
import { setupVllmConfigMock, setupVllmConfigMockWithQueryParams, setupV1ModelsMock } from './fixtures/test-helpers';

test('LoadTest Sweep Mode: 타겟 변경 시 모델명 업데이트', async ({ page }) => {
  await setupVllmConfigMock(page, {
    model_name: 'model-a',
    max_num_seqs: '128',
    gpu_memory_utilization: '0.85',
    max_model_len: '4096',
    max_num_batched_tokens: '1024',
    block_size: '16',
    swap_space: '2',
  });
  await setupV1ModelsMock(page, [{ id: 'model-a' }]);

  await page.goto('/');
  await page.getByRole('tab', { name: 'Load Test' }).waitFor({ state: 'visible', timeout: 10000 });

  await page.getByRole('tab', { name: 'Load Test' }).click();
  await page.getByTestId('loadtest-target-selector-trigger').waitFor({ state: 'visible', timeout: 10000 });
  await page.getByTestId('loadtest-target-selector-trigger').click();

  const dropdown = page.getByTestId('loadtest-target-selector-dropdown');
  await dropdown.waitFor({ state: 'visible', timeout: 5000 });
  await dropdown.locator('div[role="option"]').first().click();

  await page.getByRole('button', { name: 'Sweep Test' }).click();

  const modelInput = page.getByLabel('Model');
  await expect(modelInput).toBeVisible();
  const modelValue = await modelInput.inputValue();

  expect(modelValue).toBe('model-a');
});

test('Tuner: 타겟 변경 시 설정 업데이트', async ({ page }) => {
  await setupVllmConfigMockWithQueryParams(page, {
    'target-a': {
      model_name: 'model-a',
      max_num_seqs: '128',
      gpu_memory_utilization: '0.85',
      max_model_len: '4096',
      max_num_batched_tokens: '1024',
      block_size: '16',
      swap_space: '2',
    },
    'target-b': {
      model_name: 'model-b',
      max_num_seqs: '256',
      gpu_memory_utilization: '0.90',
      max_model_len: '8192',
      max_num_batched_tokens: '2048',
      block_size: '32',
      swap_space: '4',
    },
    'default': {
      model_name: 'default-model',
      max_num_seqs: '64',
      gpu_memory_utilization: '0.80',
      max_model_len: '2048',
      max_num_batched_tokens: '512',
      block_size: '8',
      swap_space: '1',
    },
  });

  await setupV1ModelsMock(page, [{ id: 'model-a' }, { id: 'model-b' }]);

  await page.route('**/api/config', async (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        vllm_endpoint: '',
        vllm_namespace: 'test-ns',
        vllm_is_name: 'target-a',
        cr_type: 'inferenceservice',
      }),
    });
  });

  await page.route('**/api/config/default-targets', async (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        isvc: { name: '', namespace: '' },
        llmisvc: { name: 'target-b', namespace: 'test-ns' },
        configmap_updated: true,
      }),
    });
  });

  await page.route('**/api/tuner/all', async (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: { running: false, trials_completed: 0 },
        trials: [],
        importance: {},
      }),
    });
  });

  await page.goto('/');
  await page.getByRole('tab', { name: 'Auto Tuner' }).waitFor({ state: 'visible', timeout: 10000 });

  await page.getByRole('tab', { name: 'Auto Tuner' }).click();

  await page.waitForFunction(() => {
    const selector = document.querySelector('[data-testid="tuner-target-selector"]');
    if (!selector) return false;
    const trigger = selector.querySelector('.target-selector-trigger');
    return trigger !== null;
  }, { timeout: 10000 });

  const trigger = page.getByTestId('tuner-target-selector-trigger');
  await trigger.waitFor({ state: 'visible', timeout: 10000 });
  await trigger.click();

  const dropdown = page.getByTestId('tuner-target-selector-dropdown');
  await dropdown.waitFor({ state: 'visible', timeout: 5000 });
  const options = dropdown.locator('div[role="option"]');
  await expect(options).toHaveCount(2);

  await dropdown.locator('div[role="option"]', { hasText: 'target-a' }).click();

  await page.waitForFunction(() => {
    const input = document.querySelector('input[aria-label="max_num_seqs min"]');
    return input && (input as HTMLInputElement).value !== '';
  }, { timeout: 5000 });

  const maxNumSeqsRow = page.locator('tr').filter({ hasText: 'max_num_seqs' });
  const maxNumSeqsMin = maxNumSeqsRow.locator('input[type="number"]').first();
  await expect(maxNumSeqsMin).toBeVisible();
  const firstValue = await maxNumSeqsMin.inputValue();
  expect(firstValue).toBe('128');

  await trigger.click();
  await dropdown.waitFor({ state: 'visible', timeout: 5000 });

  await dropdown.locator('div[role="option"]', { hasText: 'target-b' }).click();

  await page.waitForTimeout(500);

  const secondValue = await maxNumSeqsMin.inputValue();
  expect(secondValue).toBe('256');
});
