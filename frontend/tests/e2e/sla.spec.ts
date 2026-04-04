import { test, expect } from './fixtures/mock-api';

test('SLA 탭에서 프로필 목록 렌더링', async ({ page, mockApi }) => {
  await page.goto('/');

  await page.getByRole('tab', { name: 'SLA' }).click();

  await expect(page.getByText('새 SLA 프로필 생성')).toBeVisible();
  await expect(page.getByText('SLA 프로필 목록')).toBeVisible();
});
