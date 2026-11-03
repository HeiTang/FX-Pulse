import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import astroConfig from '../../astro.config.mjs';
import ratesData from '../../src/data/rates.json' with { type: 'json' };
import {
  availableDates,
  currencies,
  historyDates,
  periodComparison,
  historyRanges,
  rateEntries,
} from '../../src/lib/rates';
import { formatMoney } from '../../src/lib/results';

const latest = availableDates(ratesData.rates).at(-1)!;
const site = new URL('/', astroConfig.site).origin;

for (const [path, code, name] of [
  ['/', 'JPY', '外幣'] as const,
  ...Object.entries(currencies).map(
    ([code, info]) => [`/${code.toLowerCase()}/`, code, info.name] as const,
  ),
]) {
  test(`${path} has crawlable content and share metadata without JavaScript`, async ({
    browser,
    request,
    baseURL,
  }) => {
    const context = await browser.newContext({
      javaScriptEnabled: false,
      baseURL,
    });
    const page = await context.newPage();
    try {
      await page.goto(path);
      await expect(page.locator('.header-updated time')).toHaveAttribute(
        'datetime',
        ratesData.meta.last_updated,
      );
      await expect(page.locator('.header-updated')).toHaveText(
        /最後更新 \d{4}-\d{2}-\d{2} \d{2}:\d{2}/,
      );
      await expect(page.locator('.site-footer time')).toHaveCount(0);
      await expect(page.locator('.view-tabs')).toBeVisible();
      await expect(page.locator('.view-tabs a')).toHaveCount(3);
      for (const id of ['view-chart', 'view-history', 'view-method'])
        await expect(page.locator(`#${id}`)).toBeVisible();
      await expect(page.locator('#view-method .guide-source')).toHaveCount(3);
      await expect(page.locator('#view-method')).toContainText('外幣金額');
      await expect(page.locator('.guide-jcb-formula')).toContainText(
        '每美元兌台幣賣出價',
      );
      await expect(page.locator('.guide-jcb-formula')).toContainText(
        '每美元兌外幣買入價',
      );
      await expect(page.locator('#view-method')).toContainText(
        '使用同日 JCB 美元基準表；美元的分母為 1，缺資料日不沿用前值。',
      );
      const ranges = historyRanges(
        ratesData.rates,
        availableDates(ratesData.rates).slice(-7),
        code,
      );
      await expect(page.locator('.range-item')).toHaveCount(3);
      for (const [index, range] of ranges.entries()) {
        const item = page.locator('.range-item').nth(index);
        if (range.count < 7)
          await expect(item).toContainText(`${range.count} / 7 筆`);
        if (range.latest) {
          await expect(item.locator('time')).toHaveAttribute(
            'datetime',
            range.latest.date,
          );
          await expect(item.locator('.range-latest strong')).toHaveText(
            range.latest.rate.toFixed(6),
          );
          await expect(item.locator('.range-bounds')).toContainText(
            `最低 ${range.lowest!.toFixed(6)}`,
          );
          await expect(item.locator('.range-bounds')).toContainText(
            `最高 ${range.highest!.toFixed(6)}`,
          );
        }
      }
      await expect(page).toHaveTitle(
        `${name}刷卡匯率比較與試算｜VISA、Mastercard、JCB — FX Pulse`,
      );
      await expect(page.locator('h1')).toHaveText(`${name}刷卡匯率比較與試算`);
      await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
        'href',
        `${site}${path}`,
      );
      await expect(page.locator('meta[property="og:url"]')).toHaveAttribute(
        'content',
        `${site}${path}`,
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
      expect(image).toBe(`${site}/og/fx-pulse.png`);
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
      await expect(page.locator('.page-intro')).toHaveCount(0);
      await expect(page.locator('header h1')).toHaveText(
        `${name}刷卡匯率比較與試算`,
      );
      for (const code of Object.keys(currencies)) {
        await expect(
          page.locator(`.currency-shortcuts a[href="/${code.toLowerCase()}/"]`),
        ).toHaveCount(1);
      }
      if (path !== '/') {
        const history = page.locator('.rate-guide .rate-history');
        await expect(history.locator('tbody tr')).toHaveCount(7);
        const row = history.locator('tbody tr').first();
        await expect(row).toContainText(latest);
        for (const entry of rateEntries(ratesData.rates, code, latest))
          await expect(row).toContainText(entry.rate.toFixed(6));
        expect(
          await history.evaluate(
            (element) => element.scrollWidth <= element.clientWidth + 1,
          ),
        ).toBe(true);
      }
      await expect(page.locator('#jpy-summary')).toHaveCount(0);
      await expect(page.locator('.period-comparison')).toHaveCount(1);
      await page.locator('.period-comparison summary').click();
      const comparison = periodComparison(
        ratesData.rates,
        historyDates(availableDates(ratesData.rates), latest, '7'),
        code,
      );
      await expect(page.locator('#period-context')).toHaveText(
        `近 7 天 · ${code} · 三家比較`,
      );
      await expect(page.locator('#period-dates')).toHaveText(`截至 ${latest}`);
      await expect(page.locator('#period-count')).toHaveText(
        `${comparison.count} 天`,
      );
      for (const src of ['VISA', 'Mastercard', 'JCB'] as const)
        await expect(page.locator(`#period-${src.toLowerCase()}`)).toHaveText(
          `${comparison.bestDays[src]} 天`,
        );
      await expect(page.locator('#period-tied')).toHaveText(
        `${comparison.tied} 天`,
      );
      for (const field of ['median', 'maximum'] as const)
        await expect(page.locator(`#period-${field}`)).toHaveText(
          comparison[field] === null
            ? '—'
            : `約 NT$ ${formatMoney(comparison[field], 'TWD')}`,
        );
    } finally {
      await context.close();
    }
  });
}

test('JPY uses one statistics panel for initial HTML and interactive updates', async ({
  page,
}) => {
  await page.goto('/jpy/');
  await page.locator('.period-comparison summary').click();
  await page.locator('[data-range="30"]').click();
  const comparison = periodComparison(
    ratesData.rates,
    historyDates(availableDates(ratesData.rates), latest, '30'),
    'JPY',
    200,
    true,
  );
  await page.locator('#amount').fill('200');
  await page.locator('#swap-direction').click();
  await expect(page.locator('#period-context')).toHaveText(
    '近 30 天 · JPY · 三家比較',
  );
  await expect(page.locator('#period-amount')).toHaveText(
    '換算 200.00 TWD → JPY',
  );
  await expect(page.locator('#period-median')).toHaveText(
    comparison.median === null
      ? '—'
      : `約 JPY ${formatMoney(comparison.median, 'JPY')}`,
  );
  await expect(page.locator('.period-comparison')).toHaveCount(1);
  await expect(page.locator('#jpy-summary')).toHaveCount(0);
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test('USD page keeps its default on reload and query links can override it', async ({
  page,
}) => {
  await page.goto('/usd/');
  await expect(page.locator('#currency')).toHaveValue('USD');
  await expect(page.locator('#route-name')).toHaveText('美元');
  await expect(page).toHaveURL(
    (url) => url.pathname === '/usd/' && !url.searchParams.has('currency'),
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
  await expect(page.locator('.rate-history caption')).toContainText('日圓');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    `${site}/jpy/`,
  );
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test('sitemap lists the home and all currency pages', async ({ request }) => {
  const response = await request.get('/sitemap.xml');
  expect(response.ok()).toBe(true);
  const xml = await response.text();
  expect(xml.match(/<loc>/g)).toHaveLength(Object.keys(currencies).length + 1);
  for (const path of [
    '/',
    ...Object.keys(currencies).map((code) => `/${code.toLowerCase()}/`),
  ])
    expect(xml).toContain(`<loc>${site}${path}</loc>`);
});

test('robots allows crawling and points to the configured sitemap', async ({
  request,
}) => {
  const response = await request.get('/robots.txt');
  expect(response.ok()).toBe(true);
  expect(await response.text()).toBe(
    `User-agent: *\nAllow: /\n\nSitemap: ${site}/sitemap.xml\n`,
  );
});
