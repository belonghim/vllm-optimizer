import { test, expect } from './fixtures/mock-api';

test('벤치마크 탭에서 목록 조회', async ({ page, mockApi: _mockApi }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('vllm-opt-mock-enabled', 'false');
  });
  await page.goto('/');

  await page.getByRole('tab', { name: 'Benchmark' }).click();

  await expect(page.getByText('Saved load test results will appear here.')).toBeVisible();
});
