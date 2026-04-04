import { test, expect } from './fixtures/mock-api';

test('클러스터 설정 바에서 설정 저장', async ({ page, mockApi: _mockApi }) => {
  await page.route('**/api/config', async (route) => {
    if (route.request().method() === 'PATCH') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    }
  });

  await page.goto('/');

  await page.getByRole('tab', { name: 'Auto Tuner' }).click();

  const endpointInput = page.getByLabel('vLLM Endpoint');
  const namespaceInput = page.getByLabel('Namespace');
  const isvcInput = page.getByLabel('InferenceService');

  const currentEndpoint = await endpointInput.inputValue();
  const currentNamespace = await namespaceInput.inputValue();
  const currentIsvc = await isvcInput.inputValue();

  await endpointInput.fill(currentEndpoint || 'http://openshift-ai-inference-openshift-default.openshift-ingress.svc/llm-d-demo/small-llm-d');
  await namespaceInput.fill(`${currentNamespace || 'llm-d'}-demo`);
  await isvcInput.fill(currentIsvc || 'small-llm-d');

  const saveButton = page.getByRole('button', { name: '💾 Save' });
  await expect(saveButton).toBeEnabled();

  const patchResponse = page.waitForResponse((response) =>
    response.url().includes('/api/config') && response.request().method() === 'PATCH'
  );
  await saveButton.click();

  const response = await patchResponse;
  expect(response.ok()).toBeTruthy();
});