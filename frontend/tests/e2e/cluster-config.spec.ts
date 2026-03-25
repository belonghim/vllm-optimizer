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
    if (pathname === '/api/config' && method === 'PATCH') {
      return json({ success: true });
    }
    if (pathname === '/api/sla/profiles' && method === 'GET') {
      return json([]);
    }

    return json({});
  });
}

test('클러스터 설정 바에서 설정 저장', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');

  await page.getByRole('tab', { name: '자동 파라미터 튜닝' }).click();

  const endpointInput = page.getByLabel('vLLM Endpoint');
  const namespaceInput = page.getByLabel('Namespace');
  const isvcInput = page.getByLabel('InferenceService');

  const currentEndpoint = await endpointInput.inputValue();
  const currentNamespace = await namespaceInput.inputValue();
  const currentIsvc = await isvcInput.inputValue();

  await endpointInput.fill(currentEndpoint || 'http://llm-ov-predictor.test.svc.cluster.local:8080');
  await namespaceInput.fill(`${currentNamespace || 'vllm-lab'}-e2e`);
  await isvcInput.fill(currentIsvc || 'llm-ov');

  const saveButton = page.getByRole('button', { name: '💾 Save' });
  await expect(saveButton).toBeEnabled();

  const patchResponse = page.waitForResponse((response) =>
    response.url().includes('/api/config') && response.request().method() === 'PATCH'
  );
  await saveButton.click();

  const response = await patchResponse;
  expect(response.ok()).toBeTruthy();
});
