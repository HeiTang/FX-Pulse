import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import ratesData from '../../src/data/rates.json' with { type: 'json' };
import { availableDates, rateEntries } from '../../src/lib/rates';

const latest = availableDates(ratesData.rates).at(-1)!;

for (const [path, code, name] of [
  ['/', 'JPY', '外幣'],
  ['/jpy/', 'JPY', '日圓'],
  ['/usd/', 'USD', '美元'],
] as const) {
  test(`${path} has crawlable content and share metadata without JavaScript`, async ({
    browser,
    request,
  }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    try {
      await page.goto(`http://127.0.0.1:4322${path}`);
      await expect(page).toHaveTitle(
        `${name}刷卡匯率比較與試算｜VISA、Mastercard、JCB — FX Pulse`,
      );
      await expect(page.locator('h1')).toHaveText(`${name}刷卡匯率比較與試算`);
      await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
        'href',
        `https://fx.purr.tw${path}`,
      );
      await expect(page.locator('meta[property="og:url"]')).toHaveAttribute(
        'content',
        `https://fx.purr.tw${path}`,
      );
      await expect(page.locator('meta[name="description"]')).toHaveAttribute(
        'content',
        /JCB.*估算/,
      );
      await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute(
        'content',
        'summary_large_image',
      );
      const image = await page
        .locator('meta[property="og:image"]')
        .getAttribute('content');
      expect(image).toBe('https://fx.purr.tw/og/fx-pulse.png');
      const response = await request.get('/og/fx-pulse.png');
      expect(response.ok()).toBe(true);
      const png = await response.body();
      expect(png.subarray(1, 4).toString()).toBe('PNG');
      expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([1200, 630]);
      await expect(page.locator('#currency')).toHaveValue(code);
      await expect(page.locator('#comparison-context')).toHaveText(
        `${code} → TWD`,
      );
      for (const entry of rateEntries(ratesData.rates, code, latest)) {
        const row = page.locator('.result-row').filter({ hasText: entry.src });
        await expect(row).toContainText(`1 ${code} =`);
      }
      for (const href of ['/', '/jpy/', '/usd/']) {
        await expect(
          page.locator(`nav[aria-label="刷卡匯率頁面"] a[href="${href}"]`),
        ).toHaveCount(1);
      }
      if (path !== '/') {
        await expect(page.locator('.rate-history tbody tr')).toHaveCount(7);
        const row = page.locator('.rate-history tbody tr').first();
        await expect(row).toContainText(latest);
        for (const entry of rateEntries(ratesData.rates, code, latest))
          await expect(row).toContainText(entry.rate.toFixed(6));
      }
    } finally {
      await context.close();
    }
  });
}

test('USD page keeps its default on reload and query links can override it', async ({
  page,
}) => {
  await page.goto('/usd/');
  await expect(page.locator('#currency')).toHaveValue('USD');
  await expect(page.locator('#route-name')).toHaveText('美元');
  await expect(page).toHaveURL(
    (url) =>
      url.pathname === '/usd/' && url.searchParams.get('currency') === 'USD',
  );
  await page.locator('#amount').fill('200');
  await expect(page).toHaveURL(
    (url) => url.searchParams.get('amount') === '200',
  );
  await page.reload();
  await expect(page.locator('#amount')).toHaveValue('200');
  await expect(page.locator('#comparison-context')).toHaveText('USD → TWD');
  await page.goto('/usd/?currency=JPY&amount=1000');
  await expect(page.locator('#comparison-context')).toHaveText('JPY → TWD');
  await expect(page.locator('.rate-history caption')).toContainText('美元');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    'https://fx.purr.tw/usd/',
  );
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test('sitemap lists all three canonical pages', async ({ request }) => {
  const response = await request.get('/sitemap.xml');
  expect(response.ok()).toBe(true);
  const xml = await response.text();
  for (const path of ['/', '/jpy/', '/usd/'])
    expect(xml).toContain(`<loc>https://fx.purr.tw${path}</loc>`);
});
