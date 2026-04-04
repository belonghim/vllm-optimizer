import { type Page } from '@playwright/test';

export interface VllmConfigMock {
  model_name: string;
  max_num_seqs: string;
  gpu_memory_utilization: string;
  max_model_len: string;
  max_num_batched_tokens: string;
  block_size: string;
  swap_space: string;
}

export async function setupVllmConfigMock(page: Page, configs: VllmConfigMock) {
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
      return json({ success: true, data: configs });
    }
  });
}

export async function setupV1ModelsMock(page: Page, models: { id: string }[]) {
  await page.route('**/v1/models', async (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        object: 'list',
        data: models.map(m => ({ id: m.id, object: 'model' })),
      }),
    });
  });
}
