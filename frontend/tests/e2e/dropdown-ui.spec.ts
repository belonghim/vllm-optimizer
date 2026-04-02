import { test, expect, type Page } from '@playwright/test';

const ISVC_TARGET_1 = { namespace: 'vllm-lab-dev', inferenceService: 'llm-ov', crType: 'inferenceservice', isDefault: true };
const ISVC_TARGET_2 = { namespace: 'vllm-lab-prod', inferenceService: 'llm-prod', crType: 'inferenceservice', isDefault: false };

interface ClusterTarget {
  namespace: string;
  inferenceService: string;
  crType?: string;
  isDefault: boolean;
}

async function mockConfigApi(page: Page, targets: ClusterTarget[] = [ISVC_TARGET_1]) {
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const { pathname, searchParams } = new URL(req.url());
    const method = req.method();
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (pathname === '/api/config' && method === 'GET') {
      const defaultTarget = targets.find(t => t.isDefault) || targets[0];
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
        const key = `${target.namespace}/${target.inferenceService}`;
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
}

test.describe('TargetSelector Dropdown UI', () => {
  test.beforeEach(async ({ page }) => {
    await mockConfigApi(page, [ISVC_TARGET_1, ISVC_TARGET_2]);
    await page.goto('/');
    await page.getByRole('tab', { name: 'Auto Tuner' }).click();
    await page.waitForSelector('[data-testid="tuner-target-selector"]', { timeout: 10000 });
  });

  test('displays dropdown trigger button', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await expect(triggerBtn).toBeVisible();
    await expect(triggerBtn).toHaveAttribute('aria-haspopup', 'listbox');
  });

  test('opens dropdown on click', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.click();

    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    await expect(dropdown).toBeVisible();
    await expect(dropdown).toHaveAttribute('role', 'listbox');
  });

  test('closes dropdown on outside click', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.click();

    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    await expect(dropdown).toBeVisible();

    await page.click('body', { position: { x: 10, y: 10 } });
    await expect(dropdown).not.toBeVisible();
  });

  test('closes dropdown on Escape key', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.click();

    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    await expect(dropdown).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(dropdown).not.toBeVisible();
  });

  test('displays default marker (★) for default target', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.click();

    const defaultOption = page.locator('.target-selector-option').first();
    await expect(defaultOption.locator('.target-selector-option-star')).toContainText('★');
  });

  test('selects option on click', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.click();

    const options = page.locator('.target-selector-option');
    await options.nth(1).click();

    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    await expect(dropdown).not.toBeVisible();

    await expect(triggerBtn).toContainText(ISVC_TARGET_2.inferenceService);
  });

  test('supports keyboard navigation with ArrowDown', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.focus();
    await triggerBtn.click();

    await page.keyboard.press('ArrowDown');

    const highlightedOption = page.locator('.target-selector-option.highlighted');
    await expect(highlightedOption).toBeVisible();
  });

  test('supports keyboard navigation with ArrowUp', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.focus();
    await triggerBtn.click();

    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowUp');

    const highlightedOption = page.locator('.target-selector-option.highlighted');
    await expect(highlightedOption).toBeVisible();
  });

  test('selects option with Enter key', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await triggerBtn.focus();
    await triggerBtn.click();

    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');

    const dropdown = page.locator('[data-testid="tuner-target-selector-dropdown"]');
    await expect(dropdown).not.toBeVisible();
  });

  test('displays namespace in parentheses', async ({ page }) => {
    const triggerBtn = page.locator('[data-testid="tuner-target-selector-trigger"]');
    await expect(triggerBtn).toContainText(`(${ISVC_TARGET_1.namespace})`);
  });
});

test.describe('MultiTargetSelector Dropdown UI', () => {
  test.beforeEach(async ({ page }) => {
    await mockConfigApi(page, [ISVC_TARGET_1]);
    await page.goto('/');
    await page.getByRole('tab', { name: 'Monitoring' }).click();
    await page.waitForSelector('.multi-target-selector', { timeout: 10000 });
  });

  test('displays dropdown toggle button', async ({ page }) => {
    const dropdownBtn = page.locator('[data-testid="dropdown-toggle-btn"]');
    await expect(dropdownBtn).toBeVisible();
    await expect(dropdownBtn).toContainText(ISVC_TARGET_1.inferenceService);
  });

  test('opens dropdown panel on click', async ({ page }) => {
    const dropdownBtn = page.locator('[data-testid="dropdown-toggle-btn"]');
    await dropdownBtn.click();

    const dropdownPanel = page.locator('.multi-target-dropdown-panel');
    await expect(dropdownPanel).toBeVisible();
  });

  test('displays default marker (★) for default target', async ({ page }) => {
    const defaultRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(defaultRow).toBeVisible();
    await expect(defaultRow.locator('.default-star')).toContainText('★');
  });

  test('displays namespace under target name', async ({ page }) => {
    const targetRow = page.locator('[data-testid^="target-row-"]').first();
    await expect(targetRow).toBeVisible();
    await expect(targetRow.locator('.target-ns')).toContainText(ISVC_TARGET_1.namespace);
  });

  test('displays arrow direction based on dropdown state', async ({ page }) => {
    const dropdownBtn = page.locator('[data-testid="dropdown-toggle-btn"]');
    const arrow = dropdownBtn.locator('.dropdown-arrow');

    await expect(arrow).toContainText('▼');

    await dropdownBtn.click();
    await expect(arrow).toContainText('▲');

    await dropdownBtn.click();
    await expect(arrow).toContainText('▼');
  });
});

test.describe('Dropdown UI Accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await mockConfigApi(page, [ISVC_TARGET_1, ISVC_TARGET_2]);
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