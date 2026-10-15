import { expect, test } from '@playwright/test';

test('production page inlines its styles', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('link[rel="stylesheet"]')).toHaveCount(0);
  await expect(page.locator('head style')).not.toHaveCount(0);
  await expect(page.locator('.result-row')).toHaveCount(3);
});

test('offscreen chart loads on approach with the current selection', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 600 });
  const chartRequests: string[] = [];
  page.on('request', (request) => {
    if (/\/_astro\/chart\.[^/]+\.js$/.test(request.url()))
      chartRequests.push(request.url());
  });
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  expect(chartRequests).toHaveLength(0);
  await expect(page.locator('#chart canvas')).toHaveCount(0);

  await page.locator('[data-quick-currency="USD"]').click();
  await page.locator('#amount').fill('20000');
  await expect(page.locator('#chart-title')).toHaveText('USD / TWD');
  await expect(page.locator('.result-row')).toHaveCount(3);
  expect(chartRequests).toHaveLength(0);

  await page.locator('#chart').scrollIntoViewIfNeeded();
  await expect(page.locator('#chart canvas')).toHaveCount(1);
  expect(chartRequests).toHaveLength(1);
  await expect(page.locator('#chart')).toHaveAttribute(
    'aria-label',
    /^USD 對 TWD/,
  );
  await page.locator('[data-range="30"]').click();
  await expect(page.locator('[data-range="30"]')).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.locator('#chart canvas')).toHaveCount(1);
  expect(chartRequests).toHaveLength(1);
});
