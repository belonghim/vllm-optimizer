import { test, expect } from './fixtures/mock-api';

test.skip('튜너 탭에서 시작 폼 렌더링', async ({ page, mockApi }) => {
  await page.goto('/');
  await page.waitForTimeout(3000);

  await page.getByRole('tab', { name: 'Auto Tuner' }).click();
  await page.waitForTimeout(2000);

  await expect(page.getByText('Bayesian Optimization 설정')).toBeVisible();
  await expect(page.getByLabel('완료 후 벤치마크 자동 저장')).toBeVisible();
});
