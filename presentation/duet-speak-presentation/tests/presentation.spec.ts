import { expect, test } from '@playwright/test';

test('loads, navigates fragments, overview and direct routes', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/#/s04-f0');
  await expect(page.locator('[data-slide-id="s04"]')).toBeVisible();
  await page.keyboard.press('ArrowRight');
  await expect(page).toHaveURL(/s04-f1/);
  await page.keyboard.press('o');
  await expect(page.getByRole('dialog', { name: 'Tổng quan các slide' })).toBeVisible();
  await page.getByRole('button', { name: /Kết quả ASR/ }).click();
  await expect(page.locator('[data-slide-id="s10"]')).toBeVisible();
  await page.reload();
  await expect(page.locator('[data-slide-id="s10"]')).toBeVisible();
  await page.keyboard.press('a');
  await expect(page.locator('[data-slide-id="a01"]')).toBeVisible();
  expect(errors).toEqual([]);
});

test('supports reverse, notes, hidden controls, appendix and rapid navigation', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/#/s06-f0');
  await page.keyboard.press('PageDown');
  await expect(page).toHaveURL(/s06-f1/);
  await page.keyboard.press('PageUp');
  await expect(page).toHaveURL(/s06-f0/);
  await page.keyboard.press('n');
  await expect(page.locator('.presenter-notes')).toBeVisible();
  await page.keyboard.press('Escape');
  await page.keyboard.press('m');
  await expect(page.locator('.deck-controls')).toHaveCount(0);
  await page.keyboard.press('m');
  await expect(page.locator('.deck-controls')).toBeVisible();
  await page.keyboard.press('a');
  await expect(page.locator('[data-slide-id="a01"]')).toBeVisible();
  for (let index = 0; index < 12; index += 1) await page.keyboard.press('ArrowRight');
  expect(errors).toEqual([]);
});

test('print mode renders all slides with no controls', async ({ page }) => {
  await page.goto('/?print=1');
  await expect(page.locator('.print-deck > .slide')).toHaveCount(18);
  await expect(page.locator('.deck-controls')).toHaveCount(0);
});
