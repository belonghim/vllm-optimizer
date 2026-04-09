import { test, expect } from './fixtures/mock-api';

test('SLA 탭에서 프로필 목록 렌더링', async ({ page, mockApi }) => {
  await page.goto('/');

  await page.getByRole('tab', { name: 'SLA' }).click();

  await expect(page.getByText('Create New SLA Profile')).toBeVisible();
  await expect(page.getByText('SLA Profile List')).toBeVisible();
});

test('SLA 폼에서 새로운 threshold 필드들이 표시됨', async ({ page, mockApi }) => {
  await page.goto('/');
  await page.getByRole('tab', { name: 'SLA' }).click();

  await expect(page.getByLabel('TPOT Mean (ms)')).toBeVisible();
  await expect(page.getByLabel('TPOT P95 (ms)')).toBeVisible();
  await expect(page.getByLabel('Queue Time Mean (ms)')).toBeVisible();
  await expect(page.getByLabel('Queue Time P95 (ms)')).toBeVisible();
  await expect(page.getByLabel('Mean E2E Latency (ms)')).toBeVisible();
});

test('SLA 폼 제출 시 프로필 생성됨', async ({ page, mockApi }) => {
  await page.goto('/');
  await page.getByRole('tab', { name: 'SLA' }).click();

  await page.getByLabel('Profile Name *').fill('Test SLA Profile');
  await page.getByLabel('TPOT Mean (ms)').fill('100');

  await page.getByRole('button', { name: 'Create Profile' }).click();

  await expect(page.getByLabel('Profile Name *')).toHaveValue('');
  await expect(page.getByLabel('TPOT Mean (ms)')).toHaveValue('');
});

test.skip('SLA 차트에서 새로운 메트릭 선택 가능', async ({ page, mockApi }) => {
  await page.goto('/');
  await page.getByRole('tab', { name: 'SLA' }).click();

  await page.getByLabel('Profile Name *').fill('Test SLA Profile');
  await page.getByLabel('TPOT Mean (ms)').fill('100');
  await page.getByRole('button', { name: 'Create Profile' }).click();

  await page.waitForTimeout(1000);

  const radio = page.locator('input[name="sla-profile"]').first();
  await expect(radio).toBeVisible({ timeout: 15000 });
  await radio.click();

  await page.waitForTimeout(500);

  await expect(page.getByRole('button', { name: 'TPOT Mean' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'TPOT P95' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Queue Mean' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Queue P95' })).toBeVisible();
});
