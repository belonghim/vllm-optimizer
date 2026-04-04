import { test, expect } from './fixtures/mock-api';

const ISVC_TARGET_1 = { namespace: 'vllm-lab-dev', inferenceService: 'llm-ov', crType: 'inferenceservice', isDefault: true };
const ISVC_TARGET_2 = { namespace: 'vllm-lab-prod', inferenceService: 'llm-prod', crType: 'inferenceservice', isDefault: false };

test.describe('Dropdown UI Accessibility', () => {
  test.beforeEach(async ({ page, mockApi: _mockApi }) => {
    await page.unrouteAll({ behavior: 'ignoreErrors' });
    await page.route('**/api/**', async (route) => {
      const req = route.request();
      const { pathname, searchParams } = new URL(req.url());
      const method = req.method();
      const json = (body: unknown) => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });

      const targets = [ISVC_TARGET_1, ISVC_TARGET_2];
      const defaultTarget = targets.find(t => t.isDefault) || targets[0];

      if (pathname === '/api/config' && method === 'GET') {
        return json({
          vllm_endpoint: `http://${defaultTarget.inferenceService}-predictor.${defaultTarget.namespace}.svc.cluster.local:8080`,
          vllm_namespace: defaultTarget.namespace,
          vllm_is_name: defaultTarget.inferenceService,
          cr_type: defaultTarget.crType || 'inferenceservice',
          resolved_model_name: 'test-model',
        });
      }

      if (pathname === '/api/config' && method === 'PATCH') {
        return json({ success: true, cr_type: 'inferenceservice' });
      }

      if (pathname === '/api/config/default-targets' && method === 'PATCH') {
        return json({ success: true });
      }

      if (pathname === '/api/sla/profiles' && method === 'GET') {
        return json([]);
      }

      if (pathname === '/api/metrics/latest' && method === 'GET') {
        const ns = searchParams.get('namespace') || 'vllm-lab-dev';
        const isName = searchParams.get('is_name') || 'llm-ov';
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

      if (pathname === '/api/metrics/batch' && method === 'POST') {
        const results: Record<string, unknown> = {};
        for (const target of targets) {
          const crType = target.crType || 'inferenceservice';
          const key = `${target.namespace}/${target.inferenceService}/${crType}`;
          results[key] = {
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
          };
        }
        return json({ results });
      }

      return json({});
    });

    await page.goto('/');
    await page.getByRole('tab', { name: 'Auto Tuner' }).click();
    await page.waitForSelector('[data-testid="tuner-target-selector"]', { timeout: 10000 });
  });

  test('TargetSelector has correct ARIA attributes', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await expect(triggerBtn).toHaveAttribute('aria-haspopup', 'listbox');
    await expect(triggerBtn).toHaveAttribute('aria-expanded', 'false');

    await triggerBtn.click();
    await expect(triggerBtn).toHaveAttribute('aria-expanded', 'true');

    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    await expect(dropdown).toHaveAttribute('role', 'listbox');

    const options = page.locator('.target-selector-option');
    await expect(options.first()).toHaveAttribute('role', 'option');
  });

  test('TargetSelector options have aria-selected', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.click();

    const firstOption = page.locator('.target-selector-option').first();
    await expect(firstOption).toHaveAttribute('aria-selected', 'true');
  });

  test('TargetSelector options are keyboard focusable', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.focus();
    await triggerBtn.click();

    const options = page.locator('.target-selector-option');
    await expect(options.first()).toHaveAttribute('tabindex', '0');
  });
});
