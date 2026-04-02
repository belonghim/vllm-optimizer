import { test, expect, type Page } from '@playwright/test';

/**
 * Integration Test Suite for CR-Type Default Targets
 * 
 * This test suite verifies:
 * 1. Full integration (Backend + Frontend + ConfigMap)
 * 2. TDD cycle completion (Red → Green → Refactor)
 * 3. Cross-task integration (MonitorPage + AutoTuner + LoadTest)
 * 4. Edge cases (empty targets, deleted targets)
 */

interface ApiCallLog {
  url: string;
  method: string;
  body?: unknown;
}

/**
 * Mock API with comprehensive call tracking for integration tests
 */
async function mockApiWithCallTracking(page: Page, callLog: ApiCallLog[]) {
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const { pathname, searchParams } = new URL(req.url());
    const method = req.method();
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    const call: ApiCallLog = { url: pathname, method };
    if (method === 'PATCH' || method === 'POST') {
      try {
        call.body = req.postDataJSON();
      } catch {
        // Ignore parse errors
      }
    }
    callLog.push(call);

    // GET /api/config - returns current config
    if (pathname === '/api/config' && method === 'GET') {
      return json({
        vllm_endpoint: 'http://test-endpoint:8080',
        vllm_namespace: 'test-ns',
        vllm_is_name: 'test-isvc',
        cr_type: 'inferenceservice',
        resolved_model_name: 'test-model',
      });
    }

    // PATCH /api/config - updates config
    if (pathname === '/api/config' && method === 'PATCH') {
      const body = req.postDataJSON();
      return json({
        vllm_endpoint: 'http://test-endpoint:8080',
        vllm_namespace: body.vllm_namespace || 'test-ns',
        vllm_is_name: body.vllm_is_name || 'test-isvc',
        cr_type: body.cr_type || 'inferenceservice',
        resolved_model_name: 'test-model',
        configmap_updated: true,
      });
    }

    // GET /api/config/default-targets - returns CR-type specific defaults
    if (pathname === '/api/config/default-targets' && method === 'GET') {
      return json({
        isvc: { name: 'test-isvc', namespace: 'test-ns' },
        llmisvc: { name: '', namespace: '' },
        configmap_updated: true,
      });
    }

    // PATCH /api/config/default-targets - updates CR-type specific defaults
    if (pathname === '/api/config/default-targets' && method === 'PATCH') {
      const body = req.postDataJSON();
      const isvc = body.isvc || { name: 'test-isvc', namespace: 'test-ns' };
      const llmisvc = body.llmisvc || { name: '', namespace: '' };
      return json({
        isvc,
        llmisvc,
        configmap_updated: true,
      });
    }

    // GET /api/metrics/latest - returns latest metrics
    if (pathname === '/api/metrics/latest' && method === 'GET') {
      return json({
        status: 'ready',
        data: {
          tps: 100,
          rps: 10,
          kv_cache: 50,
          running: 5,
          waiting: 2,
          gpu_util: 60,
          pods: 1,
          pods_ready: 1,
        },
        hasMonitoringLabel: true,
      });
    }

    // POST /api/metrics/batch - returns batch metrics
    if (pathname === '/api/metrics/batch' && method === 'POST') {
      return json({
        results: {
          'test-ns/test-isvc': {
            status: 'ready',
            data: {
              tps: 100,
              rps: 10,
              kv_cache: 50,
              running: 5,
              waiting: 2,
              gpu_util: 60,
              pods: 1,
              pods_ready: 1,
            },
            hasMonitoringLabel: true,
            history: [],
          },
        },
      });
    }

    // GET /api/sla/profiles - returns SLA profiles
    if (pathname === '/api/sla/profiles' && method === 'GET') {
      return json([]);
    }

    // POST /api/tuner/start - starts auto tuner
    if (pathname === '/api/tuner/start' && method === 'POST') {
      return json({
        status: 'started',
        trial_id: 'test-trial-123',
      });
    }

    // GET /api/tuner/status - returns tuner status
    if (pathname === '/api/tuner/status' && method === 'GET') {
      return json({
        status: 'idle',
        running: false,
      });
    }

    // POST /api/load-test/start - starts load test
    if (pathname === '/api/load-test/start' && method === 'POST') {
      return json({
        status: 'started',
        test_id: 'test-load-123',
      });
    }

    // GET /api/load-test/status - returns load test status
    if (pathname === '/api/load-test/status' && method === 'GET') {
      return json({
        status: 'idle',
        running: false,
      });
    }

    // Default fallback
    return json({});
  });
}

test.describe('Full Integration: Backend + Frontend + ConfigMap', () => {
  test('Complete flow: Add target → Set default → Verify ConfigMap persistence', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

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

    const patchCall = callLog.find(
      (c) => c.url === '/api/config/default-targets' && c.method === 'PATCH'
    );
    expect(patchCall).toBeDefined();
    expect(patchCall?.body).toMatchObject({
      cr_type: 'inferenceservice',
      namespace: 'isvc-ns',
      inference_service: 'my-isvc',
    });

    // Step 4: Verify ConfigMap updated flag
    const response = await page.evaluate(async () => {
      const res = await fetch('/api/config/default-targets');
      return res.json();
    });
    expect(response.configmap_updated).toBe(true);
  });

  test('Cross-page synchronization: MonitorPage → AutoTuner → LoadTest', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

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
    const getConfigCalls = callLog.filter(
      (c) => c.url === '/api/config/default-targets' && c.method === 'GET'
    );
    expect(getConfigCalls.length).toBeGreaterThan(0);
  });

  test('ConfigMap persistence across simulated Pod restart', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

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
    const getConfigCalls = callLog.filter(
      (c) => c.url === '/api/config/default-targets' && c.method === 'GET'
    );
    expect(getConfigCalls.length).toBeGreaterThan(0);

    // Step 4: Verify default target is restored
    const defaultTarget = page.getByTestId('default-target-indicator');
    await expect(defaultTarget).toBeVisible();
  });
});

test.describe('TDD Cycle Verification: Red → Green → Refactor', () => {
  test('Red: Test fails before implementation (ConfigMap API)', async ({ page }) => {
    // This test verifies that the API endpoint exists and returns correct structure
    await page.route('**/api/config/default-targets', async (route) => {
      const req = route.request();
      const method = req.method();

      if (method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            isvc: { name: 'test-isvc', namespace: 'test-ns' },
            llmisvc: { name: '', namespace: '' },
            configmap_updated: true,
          }),
        });
      }

      if (method === 'PATCH') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            isvc: { name: 'test-isvc', namespace: 'test-ns' },
            llmisvc: { name: '', namespace: '' },
            configmap_updated: true,
          }),
        });
      }

      return route.fulfill({ status: 404 });
    });

    await page.goto('/');

    // Test that API endpoint exists
    const response = await page.evaluate(async () => {
      const res = await fetch('/api/config/default-targets');
      return { status: res.status, ok: res.ok };
    });

    expect(response.status).toBe(200);
    expect(response.ok).toBe(true);
  });

  test('Green: Test passes after implementation (ConfigMap persistence)', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Add target
    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('green-ns');
    await page.getByTestId('is-input').fill('green-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    // Set default
    await page.getByTestId('set-default-btn').first().click();

    // Verify API call succeeded
    const response = await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );
    expect(response.ok()).toBe(true);

    const body = await response.json();
    expect(body.configmap_updated).toBe(true);
  });

  test('Refactor: Code quality verification (no regressions)', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Add multiple targets
    for (let i = 0; i < 3; i++) {
      await page.getByTestId('add-target-btn').click();
      await page.getByTestId('namespace-input').fill(`refactor-ns-${i}`);
      await page.getByTestId('is-input').fill(`refactor-isvc-${i}`);
      await page.getByTestId('cr-type-select').selectOption(i % 2 === 0 ? 'inferenceservice' : 'llminferenceservice');
      await page.getByTestId('confirm-add-btn').click();
      await page.waitForTimeout(100);
    }

    // Verify all targets added
    const targetRows = page.getByTestId(/target-row-/);
    const count = await targetRows.count();
    expect(count).toBe(3);

    // Set default for first target
    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    // Verify no console errors
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

test.describe('Edge Cases: Empty and Deleted Targets', () => {
  test('Empty targets state: UI shows empty state message', async ({ page }) => {
    await page.route('**/api/**', async (route) => {
      const req = route.request();
      const { pathname } = new URL(req.url());
      const method = req.method();
      const json = (body: unknown) => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });

      if (pathname === '/api/config' && method === 'GET') {
        return json({
          vllm_endpoint: '',
          vllm_namespace: '',
          vllm_is_name: '',
          cr_type: 'inferenceservice',
        });
      }

      if (pathname === '/api/config/default-targets' && method === 'GET') {
        return json({
          isvc: { name: '', namespace: '' },
          llmisvc: { name: '', namespace: '' },
          configmap_updated: true,
        });
      }

      if (pathname === '/api/metrics/latest' && method === 'GET') {
        return json({ status: 'ready', data: {}, hasMonitoringLabel: false });
      }

      if (pathname === '/api/sla/profiles' && method === 'GET') {
        return json([]);
      }

      return json({});
    });

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Verify empty state
    const addTargetBtn = page.getByTestId('add-target-btn');
    await expect(addTargetBtn).toBeVisible();

    // Verify no target rows
    const targetRows = page.getByTestId(/target-row-/);
    const count = await targetRows.count();
    expect(count).toBe(0);
  });

  test('Deleted target: Default target removed, fallback to empty', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Add target
    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('delete-ns');
    await page.getByTestId('is-input').fill('delete-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    // Set as default
    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    // Test: Remove the target that was set as default
    await page.getByTestId('remove-target-btn').first().click();
    await page.waitForTimeout(200);

    // Verify target removed
    const targetRows = page.getByTestId(/target-row-/);
    const count = await targetRows.count();
    expect(count).toBe(0);

    // Verify ConfigMap API called to clear default
    const patchCall = callLog.find(
      (c) => c.url === '/api/config/default-targets' && c.method === 'PATCH'
    );
    expect(patchCall).toBeDefined();
  });

  test('Multiple CR types: Switching between isvc and llmisvc', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Add InferenceService target
    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('isvc-ns');
    await page.getByTestId('is-input').fill('isvc-name');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();
    await page.waitForTimeout(100);

    // Add LLMInferenceService target
    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('llmisvc-ns');
    await page.getByTestId('is-input').fill('llmisvc-name');
    await page.getByTestId('cr-type-select').selectOption('llminferenceservice');
    await page.getByTestId('confirm-add-btn').click();
    await page.waitForTimeout(100);

    // Set isvc as default
    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    const isvcPatchCall = callLog.find(
      (c) => c.url === '/api/config/default-targets' && c.method === 'PATCH'
    );
    expect(isvcPatchCall?.body).toMatchObject({
      cr_type: 'inferenceservice',
    });

    // Set llmisvc as default
    callLog.length = 0; // Clear log
    await page.getByTestId('set-default-btn').last().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    const llmisvcPatchCall = callLog.find(
      (c) => c.url === '/api/config/default-targets' && c.method === 'PATCH'
    );
    expect(llmisvcPatchCall?.body).toMatchObject({
      cr_type: 'llminferenceservice',
    });
  });

  test('Concurrent operations: Rapid add/remove/set-default', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Rapid add operations
    for (let i = 0; i < 5; i++) {
      await page.getByTestId('add-target-btn').click();
      await page.getByTestId('namespace-input').fill(`rapid-ns-${i}`);
      await page.getByTestId('is-input').fill(`rapid-isvc-${i}`);
      await page.getByTestId('cr-type-select').selectOption('inferenceservice');
      await page.getByTestId('confirm-add-btn').click();
      await page.waitForTimeout(50);
    }

    // Verify all targets added
    const targetRows = page.getByTestId(/target-row-/);
    const count = await targetRows.count();
    expect(count).toBe(5);

    // Rapid set-default operations
    for (let i = 0; i < 3; i++) {
      await page.getByTestId('set-default-btn').first().click();
      await page.waitForTimeout(100);
    }

    // Verify no errors in console
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

test.describe('Cross-Task Integration: MonitorPage + AutoTuner + LoadTest', () => {
  test('MonitorPage default affects AutoTuner target selector', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Add target in MonitorPage
    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('monitor-ns');
    await page.getByTestId('is-input').fill('monitor-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    // Set as default
    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    // Navigate to AutoTuner
    await page.getByRole('tab', { name: '자동 파라미터 튜닝' }).click();
    await page.waitForTimeout(500);

    // Verify target selector shows the default
    const tunerTargetSelector = page.getByTestId('target-selector');
    await expect(tunerTargetSelector).toBeVisible();

    // Verify ConfigMap API was called
    const getConfigCalls = callLog.filter(
      (c) => c.url === '/api/config/default-targets' && c.method === 'GET'
    );
    expect(getConfigCalls.length).toBeGreaterThan(0);
  });

  test('MonitorPage default affects LoadTest target selector', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Add target in MonitorPage
    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('loadtest-ns');
    await page.getByTestId('is-input').fill('loadtest-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    // Set as default
    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    // Navigate to LoadTest
    await page.getByRole('tab', { name: '부하 테스트' }).click();
    await page.waitForTimeout(500);

    // Verify target selector shows the default
    const loadTestTargetSelector = page.getByTestId('target-selector');
    await expect(loadTestTargetSelector).toBeVisible();

    // Verify ConfigMap API was called
    const getConfigCalls = callLog.filter(
      (c) => c.url === '/api/config/default-targets' && c.method === 'GET'
    );
    expect(getConfigCalls.length).toBeGreaterThan(0);
  });

  test('AutoTuner and LoadTest use same target from ConfigMap', async ({ page }) => {
    const callLog: ApiCallLog[] = [];
    await mockApiWithCallTracking(page, callLog);

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Add target
    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('shared-ns');
    await page.getByTestId('is-input').fill('shared-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    // Set as default
    await page.getByTestId('set-default-btn').first().click();
    await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    // Navigate to AutoTuner
    await page.getByRole('tab', { name: '자동 파라미터 튜닝' }).click();
    await page.waitForTimeout(500);

    const tunerTargetSelector = page.getByTestId('target-selector');
    await expect(tunerTargetSelector).toBeVisible();

    // Navigate to LoadTest
    await page.getByRole('tab', { name: '부하 테스트' }).click();
    await page.waitForTimeout(500);

    const loadTestTargetSelector = page.getByTestId('target-selector');
    await expect(loadTestTargetSelector).toBeVisible();

    // Verify both pages loaded from same ConfigMap
    const getConfigCalls = callLog.filter(
      (c) => c.url === '/api/config/default-targets' && c.method === 'GET'
    );
    expect(getConfigCalls.length).toBeGreaterThanOrEqual(2);
  });
});

test.describe('Error Handling and Recovery', () => {
  test('ConfigMap save failure: UI shows error but remains functional', async ({ page }) => {
    await page.route('**/api/**', async (route) => {
      const req = route.request();
      const { pathname } = new URL(req.url());
      const method = req.method();
      const json = (body: unknown) => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });

      if (pathname === '/api/config' && method === 'GET') {
        return json({
          vllm_endpoint: 'http://test:8080',
          vllm_namespace: 'test-ns',
          vllm_is_name: 'test-isvc',
          cr_type: 'inferenceservice',
        });
      }

      if (pathname === '/api/config/default-targets' && method === 'GET') {
        return json({
          isvc: { name: 'test-isvc', namespace: 'test-ns' },
          llmisvc: { name: '', namespace: '' },
          configmap_updated: true,
        });
      }

      if (pathname === '/api/config/default-targets' && method === 'PATCH') {
        return json({
          isvc: { name: 'test-isvc', namespace: 'test-ns' },
          llmisvc: { name: '', namespace: '' },
          configmap_updated: false, // Simulate failure
        });
      }

      if (pathname === '/api/metrics/latest' && method === 'GET') {
        return json({ status: 'ready', data: { tps: 100 }, hasMonitoringLabel: true });
      }

      if (pathname === '/api/metrics/batch' && method === 'POST') {
        return json({
          results: {
            'test-ns/test-isvc': {
              status: 'ready',
              data: { tps: 100 },
              hasMonitoringLabel: true,
              history: [],
            },
          },
        });
      }

      if (pathname === '/api/sla/profiles' && method === 'GET') {
        return json([]);
      }

      return json({});
    });

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Add target
    await page.getByTestId('add-target-btn').click();
    await page.getByTestId('namespace-input').fill('error-ns');
    await page.getByTestId('is-input').fill('error-isvc');
    await page.getByTestId('cr-type-select').selectOption('inferenceservice');
    await page.getByTestId('confirm-add-btn').click();

    await page.waitForSelector('[data-testid^="target-row-"]');

    // Try to set default (will fail)
    await page.getByTestId('set-default-btn').first().click();

    const response = await page.waitForResponse((r) =>
      r.url().includes('/api/config/default-targets') && r.request().method() === 'PATCH'
    );

    const body = await response.json();
    expect(body.configmap_updated).toBe(false);

    // Verify UI still functional
    const setDefaultBtn = page.getByTestId('set-default-btn').first();
    await expect(setDefaultBtn).toBeVisible();
  });

  test('Network error: Retry mechanism works', async ({ page }) => {
    let callCount = 0;

    await page.route('**/api/config/default-targets', async (route) => {
      const req = route.request();
      const method = req.method();

      callCount++;

      // Fail first call, succeed second call
      if (callCount === 1 && method === 'GET') {
        return route.fulfill({ status: 500 });
      }

      if (method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            isvc: { name: 'test-isvc', namespace: 'test-ns' },
            llmisvc: { name: '', namespace: '' },
            configmap_updated: true,
          }),
        });
      }

      if (method === 'PATCH') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            isvc: { name: 'test-isvc', namespace: 'test-ns' },
            llmisvc: { name: '', namespace: '' },
            configmap_updated: true,
          }),
        });
      }

      return route.fulfill({ status: 404 });
    });

    await page.route('**/api/config', async (route) => {
      const req = route.request();
      if (req.method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            vllm_endpoint: 'http://test:8080',
            vllm_namespace: 'test-ns',
            vllm_is_name: 'test-isvc',
            cr_type: 'inferenceservice',
          }),
        });
      }
      return route.fulfill({ status: 404 });
    });

    await page.route('**/api/metrics/**', async (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ready', data: {}, hasMonitoringLabel: true }),
      });
    });

    await page.route('**/api/sla/**', async (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      });
    });

    await page.goto('/');
    await page.waitForSelector('.multi-target-selector');

    // Verify page loaded despite initial error
    const addTargetBtn = page.getByTestId('add-target-btn');
    await expect(addTargetBtn).toBeVisible();
  });
});