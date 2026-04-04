import { test, expect } from './fixtures/mock-api';

test('LoadTest Sweep Mode: 타겟 변경 시 모델명 업데이트', async ({ page }) => {
  await page.route('**/api/vllm-config', async (route) => {
    const req = route.request();
    const { pathname, searchParams } = new URL(req.url());
    const method = req.method();
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (pathname === '/api/vllm-config' && method === 'GET') {
      const isName = searchParams.get('is_name') || '';
      const crType = searchParams.get('cr_type') || '';
      if (isName === 'target-a' || (isName === 'target-a-predictor' && crType === 'inferenceservice')) {
        return json({
          success: true,
          data: {
            model_name: 'model-a',
            max_num_seqs: '128',
            gpu_memory_utilization: '0.85',
            max_model_len: '4096',
            max_num_batched_tokens: '1024',
            block_size: '16',
            swap_space: '2',
          },
        });
      }
      if (isName === 'target-b' || (isName === 'target-b-openshift-default' && crType === 'llminferenceservice')) {
        return json({
          success: true,
          data: {
            model_name: 'model-b',
            max_num_seqs: '256',
            gpu_memory_utilization: '0.90',
            max_model_len: '8192',
            max_num_batched_tokens: '2048',
            block_size: '32',
            swap_space: '4',
          },
        });
      }
      return json({
        success: true,
        data: {
          model_name: 'default-model',
          max_num_seqs: '64',
          gpu_memory_utilization: '0.80',
          max_model_len: '2048',
          max_num_batched_tokens: '512',
          block_size: '8',
          swap_space: '1',
        },
      });
    }
  });

  await page.route('**/v1/models', async (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'list',
        data: [{ id: 'model-a', object: 'model' }],
      }),
    });
  });

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
  await page.route('**/api/vllm-config', async (route) => {
    const req = route.request();
    const { pathname, searchParams } = new URL(req.url());
    const method = req.method();
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (pathname === '/api/vllm-config' && method === 'GET') {
      const isName = searchParams.get('is_name') || '';
      const crType = searchParams.get('cr_type') || '';
      if (isName === 'target-a' || (isName === 'target-a-predictor' && crType === 'inferenceservice')) {
        return json({
          success: true,
          data: {
            model_name: 'model-a',
            max_num_seqs: '128',
            gpu_memory_utilization: '0.85',
            max_model_len: '4096',
            max_num_batched_tokens: '1024',
            block_size: '16',
            swap_space: '2',
          },
        });
      }
      if (isName === 'target-b' || (isName === 'target-b-openshift-default' && crType === 'llminferenceservice')) {
        return json({
          success: true,
          data: {
            model_name: 'model-b',
            max_num_seqs: '256',
            gpu_memory_utilization: '0.90',
            max_model_len: '8192',
            max_num_batched_tokens: '2048',
            block_size: '32',
            swap_space: '4',
          },
        });
      }
      return json({
        success: true,
        data: {
          model_name: 'default-model',
          max_num_seqs: '64',
          gpu_memory_utilization: '0.80',
          max_model_len: '2048',
          max_num_batched_tokens: '512',
          block_size: '8',
          swap_space: '1',
        },
      });
    }
  });

  await page.route('**/v1/models', async (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'list',
        data: [{ id: 'model-a', object: 'model' }],
      }),
    });
  });

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
        isvc: { name: 'target-b', namespace: 'test-ns' },
        llmisvc: { name: '', namespace: '' },
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
  await dropdown.locator('div[role="option"]').first().waitFor({ state: 'visible', timeout: 5000 });

  const options = dropdown.locator('div[role="option"]');
  const count = await options.count();

  if (count >= 2) {
    await options.first().click();
  } else if (count === 1) {
    await options.first().click();
  } else {
    throw new Error('No dropdown options found');
  }

  await page.waitForFunction(() => {
    const input = document.querySelector('input[aria-label="max_num_seqs min"]');
    return input && (input as HTMLInputElement).value !== '';
  }, { timeout: 5000 });

  const maxNumSeqsRow = page.locator('tr').filter({ hasText: 'max_num_seqs' });
  const maxNumSeqsMin = maxNumSeqsRow.locator('input[type="number"]').first();
  await expect(maxNumSeqsMin).toBeVisible();
  const firstValue = await maxNumSeqsMin.inputValue();
  expect(firstValue).toMatch(/^(64|128|256)$/);

  if (count >= 2) {
    await trigger.click();
    await dropdown.waitFor({ state: 'visible', timeout: 5000 });

    const secondOptions = dropdown.locator('div[role="option"]');
    await secondOptions.last().click();

    await page.waitForTimeout(500);

    const secondValue = await maxNumSeqsMin.inputValue();
    expect(secondValue).toMatch(/^(64|128|256)$/);
    expect(secondValue).not.toBe(firstValue);
  }
});
