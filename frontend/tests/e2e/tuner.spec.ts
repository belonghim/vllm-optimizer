import { test, expect, type Page } from '@playwright/test';

async function mockApi(page: Page) {
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
      return json({ vllm_endpoint: '', vllm_namespace: '', vllm_is_name: '' });
    }
    if (pathname === '/api/sla/profiles' && method === 'GET') {
      return json([]);
    }
    if (pathname === '/api/tuner/status' && method === 'GET') {
      return json({ running: false, trials_completed: 0 });
    }
    if (pathname === '/api/tuner/trials' && method === 'GET') {
      return json([]);
    }
    if (pathname === '/api/tuner/importance' && method === 'GET') {
      return json({});
    }
    if (pathname === '/api/vllm-config' && method === 'GET') {
      return json({
        success: true,
        data: {
          model_name: 'test-model',
          max_num_seqs: '128',
          gpu_memory_utilization: '0.85',
          max_model_len: '4096',
          max_num_batched_tokens: '1024',
          block_size: '16',
          swap_space: '2',
        },
      });
    }

    return json({});
  });
}

test.skip('튜너 탭에서 시작 폼 렌더링', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await page.waitForTimeout(3000);

  await page.getByRole('tab', { name: 'Auto Tuner' }).click();
  await page.waitForTimeout(2000);

  await expect(page.getByText('Bayesian Optimization 설정')).toBeVisible();
  await expect(page.getByLabel('완료 후 벤치마크 자동 저장')).toBeVisible();
});
