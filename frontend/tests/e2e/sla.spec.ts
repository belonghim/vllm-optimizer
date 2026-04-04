import { test, expect } from './fixtures/mock-api';

test('SLA 탭에서 프로필 목록 렌더링', async ({ page, mockApi }) => {
  await page.goto('/');

  await page.getByRole('tab', { name: 'SLA' }).click();

  await expect(page.getByText('Create New SLA Profile')).toBeVisible();
  await expect(page.getByText('SLA Profile List')).toBeVisible();
});
