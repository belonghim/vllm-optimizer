import { test, expect, type Page } from '@playwright/test';

const consoleErrors = new WeakMap<Page, string[]>();

test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  consoleErrors.set(page, errors);
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
});

async function openTuner(page: Page) {
  await page.goto('/');
  await page.getByRole('tab', { name: 'Auto Tuner' }).click();
  await expect(page.getByTestId('tuner-boot-diagnosis')).toBeVisible();
}

test('boot diagnosis card renders live diagnosis of the current target', async ({ page }) => {
  await openTuner(page);

  await page.getByTestId('tbd-run').click();
  await expect(page.getByTestId('tbd-availability')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('tbd-pod')).toBeVisible();
  await expect(page.getByText(/기동 진단 실패/)).toHaveCount(0);

  expect(consoleErrors.get(page)).toEqual([]);
});

test('failed and skipped trials render in the problem table', async ({ page }) => {
  await page.route('**/api/tuner/trials', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 1,
          status: 'failed',
          tps: 0,
          p99_latency: 0,
          score: 0,
          params: { max_model_len: 16384 },
          failure: {
            reason: 'startup failed',
            diagnoses: [
              {
                code: 'kv_cache_too_small',
                title: 'KV cache too small',
                fix: '--max-model-len=8192',
              },
            ],
          },
        },
        {
          id: 2,
          status: 'skipped',
          tps: 0,
          p99_latency: 0,
          score: 0,
          params: { max_model_len: 32768 },
          failure: { reason: 'learned_limit', diagnoses: [] },
        },
      ]),
    })
  );

  await openTuner(page);

  const table = page.getByTestId('tuner-problem-trials');
  await expect(table).toBeVisible({ timeout: 15_000 });
  await expect(table.getByTestId('problem-trial-1')).toContainText('KV cache too small');
  await expect(table.getByTestId('problem-trial-1')).toContainText('--max-model-len=8192');
  await expect(table.getByTestId('problem-trial-2')).toContainText('learned_limit');

  expect(consoleErrors.get(page)).toEqual([]);
});
