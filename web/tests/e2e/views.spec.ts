import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('data tabs keep calculation state and support keyboard navigation', async ({
  page,
}) => {
  await page.goto('/jpy/');
  const chartTab = page.getByRole('tab', { name: '匯率走勢', exact: true });
  const historyTab = page.getByRole('tab', { name: '歷史匯率', exact: true });
  const methodTab = page.getByRole('tab', {
    name: '計算與資料說明',
    exact: true,
  });
  await expect(chartTab).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#view-chart')).toBeVisible();
  await expect(page.locator('#view-history')).toBeHidden();
  await expect(page.locator('#view-method')).toBeHidden();
  await page.locator('[data-range="30"]').click();
  await page.locator('#amount').fill('200');
  await historyTab.click();
  await expect(page.locator('#view-history')).toBeVisible();
  await expect(page.locator('#view-history tbody tr')).toHaveCount(7);
  expect(
    await page
      .locator('#view-history')
      .evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
  ).toBe(true);
  await methodTab.click();
  await expect(page.locator('#view-method')).toBeVisible();
  await expect(page.locator('#view-method .guide-source')).toHaveCount(3);
  await expect(page.locator('#view-method details')).toHaveCount(0);
  await methodTab.press('Home');
  await expect(chartTab).toBeFocused();
  await expect(page.locator('#view-chart')).toBeVisible();
  await expect(page.locator('[data-range="30"]')).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.locator('#amount')).toHaveValue('200');
  await expect(page.locator('#chart canvas')).toBeVisible();
  await chartTab.press('ArrowLeft');
  await expect(methodTab).toBeFocused();
  await methodTab.press('ArrowRight');
  await expect(chartTab).toBeFocused();
  await chartTab.press('End');
  await expect(methodTab).toBeFocused();
  for (const tab of [chartTab, historyTab, methodTab]) {
    await tab.click();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  }
});
