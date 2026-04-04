import { test, expect } from './fixtures/mock-api';

test.describe('Multi-replica display', () => {
  test.beforeEach(async ({ page, mockApi }) => {
    // Override batch metrics endpoint with multi-replica data
    await page.route('**/api/metrics/batch', async (route) => {
      if (route.request().method() === 'POST') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            results: {
              'test-ns/test-model': {
                status: 'ready',
                data: {
                  tps: 150.0,
                  rps: 15.0,
                  kv_cache: 65.0,
                  running: 8,
                  waiting: 4,
                  gpu_util: 70.0,
                  gpu_mem_used: 14.0,
                  gpu_mem_total: 16.0,
                  pods: 2,
                  pods_ready: 2,
                },
                hasMonitoringLabel: true,
                history: [],
              },
            },
          }),
        });
      }
    });

    // Override pods endpoint with per-pod breakdown
    await page.route('**/api/metrics/pods', async (route) => {
      if (route.request().method() === 'POST') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            aggregated: {
              tps: 150.0,
              rps: 15.0,
              kv_cache: 65.0,
              running: 8,
              waiting: 4,
              gpu_util: 70.0,
              gpu_mem_used: 14.0,
              pods: 2,
              pods_ready: 2,
            },
            per_pod: [
              {
                pod_name: 'test-model-pod-0',
                tps: 100.0,
                rps: 10.0,
                kv_cache: 50.0,
                running: 3,
                waiting: 2,
                gpu_util: 60.0,
                gpu_mem_used: 12.0,
              },
              {
                pod_name: 'test-model-pod-1',
                tps: 200.0,
                rps: 20.0,
                kv_cache: 80.0,
                running: 5,
                waiting: 2,
                gpu_util: 80.0,
                gpu_mem_used: 16.0,
              },
            ],
          }),
        });
      }
    });

    // Override config with test namespace/model
    await page.route('**/api/config', async (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            vllm_endpoint: 'http://mock-endpoint:8080',
            vllm_namespace: 'test-ns',
            vllm_is_name: 'test-model',
          }),
        });
      }
    });
  });

  test('displays aggregated metrics for multi-replica', async ({ page }) => {
    await page.goto('/');

    await page.waitForSelector('.multi-target-selector');

    const targetRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(targetRow).toBeVisible();

    await expect(targetRow.locator('td').nth(1)).toContainText('150');
    await expect(targetRow.locator('td').nth(2)).toContainText('15');
    await expect(targetRow.locator('td').nth(5)).toContainText('65');
    await expect(targetRow.locator('td').nth(9)).toContainText('8');
    await expect(targetRow.locator('td').nth(10)).toContainText('4');
    await expect(targetRow.locator('td').nth(7)).toContainText('70');
    await expect(targetRow.locator('td').nth(11)).toContainText('2 / 2');
  });

  test('shows correct math for aggregated values', async ({ page }) => {
    await page.goto('/');

    await page.waitForSelector('.multi-target-selector');

    const targetRow = page.locator('[data-testid^="target-row-"]').first();

    const displayedTps = await targetRow.locator('td').nth(1).textContent();
    const displayedRps = await targetRow.locator('td').nth(2).textContent();
    const displayedKvCache = await targetRow.locator('td').nth(5).textContent();
    const displayedRunning = await targetRow.locator('td').nth(9).textContent();
    const displayedWaiting = await targetRow.locator('td').nth(10).textContent();
    const displayedGpuUtil = await targetRow.locator('td').nth(7).textContent();

    expect(parseFloat(displayedTps || '0')).toBe(150);
    expect(parseFloat(displayedRps || '0')).toBe(15);
    expect(parseFloat(displayedKvCache || '0')).toBe(65);
    expect(parseFloat(displayedGpuUtil || '0')).toBe(70);
    expect(parseInt(displayedRunning || '0')).toBe(8);
    expect(parseInt(displayedWaiting || '0')).toBe(4);
  });

  test('pods endpoint returns per-pod breakdown', async ({ page }) => {
    await page.goto('/');

    await page.waitForSelector('.multi-target-selector');

    const response = await page.evaluate(async () => {
      const res = await fetch('/api/metrics/pods', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          targets: [{
            namespace: 'test-ns',
            inferenceService: 'test-model',
            cr_type: 'inferenceservice'
          }]
        })
      });
      return res.json();
    });

    expect(response.aggregated).toBeDefined();
    expect(response.per_pod).toHaveLength(2);
    expect(response.per_pod[0].pod_name).toBe('test-model-pod-0');
    expect(response.per_pod[1].pod_name).toBe('test-model-pod-1');
    expect(response.per_pod[0].tps).toBe(100);
    expect(response.per_pod[1].tps).toBe(200);
  });

  test('verify average math for percentage metrics', async ({ page }) => {
    await page.goto('/');

    await page.waitForSelector('.multi-target-selector');

    const targetRow = page.locator('[data-testid^="target-row-"]').first();

    const displayedTps = await targetRow.locator('td').nth(1).textContent();
    const displayedKvCache = await targetRow.locator('td').nth(5).textContent();
    const displayedGpuUtil = await targetRow.locator('td').nth(7).textContent();

    const tps = parseFloat(displayedTps || '0');
    const kvCache = parseFloat(displayedKvCache || '0');
    const gpuUtil = parseFloat(displayedGpuUtil || '0');

    expect(tps).toBe(150);
    expect(kvCache).toBe(65);
    expect(gpuUtil).toBe(70);
  });

  test('verify sum math for count metrics', async ({ page }) => {
    await page.goto('/');

    await page.waitForSelector('.multi-target-selector');

    const targetRow = page.locator('[data-testid^="target-row-"]').first();

    const displayedRunning = await targetRow.locator('td').nth(9).textContent();
    const displayedWaiting = await targetRow.locator('td').nth(10).textContent();

    const running = parseInt(displayedRunning || '0');
    const waiting = parseInt(displayedWaiting || '0');

    expect(running).toBe(8);
    expect(waiting).toBe(4);
  });
});
