import { test, expect } from './fixtures/mock-api';

test('부하 테스트 탭에서 기본 폼 요소가 보임', async ({ page, mockApi }) => {
  await page.goto('/');

  await page.getByRole('tab', { name: 'Load Test' }).click();

  await expect(page.getByLabel('vLLM Endpoint')).toBeVisible();
  await expect(page.getByRole('button', { name: '▶ Run Load Test' })).toBeVisible();
});
