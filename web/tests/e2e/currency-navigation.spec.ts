import { expect, test } from '@playwright/test';
import ratesData from '../../src/data/rates.json' with { type: 'json' };
import {
  availableDates,
  currencies,
  historyRanges,
  rateEntries,
} from '../../src/lib/rates';
import { currencyPage } from '../../src/lib/currency-page';

test('home shortcut and legacy query both select a matching currency page', async ({
  page,
}) => {
  await page.goto('/');
  await page.locator('[data-quick-currency="JPY"]').click();
  await expect(page).toHaveURL((url) => url.pathname === '/jpy/');
  await expect(page.locator('header h1')).toHaveText(
    currencyPage('JPY').heading,
  );
  await page.goto('/?currency=USD');
  await expect(page).toHaveURL((url) => url.pathname === '/usd/');
  await expect(page.locator('header h1')).toHaveText(
    currencyPage('USD').heading,
  );
  await expect(page.locator('.history-title')).toHaveText('美元歷史匯率');
});

test('shortcuts update URL, header, metadata, history and ranges without resetting calculation', async ({
  page,
}) => {
  await page.goto('/jpy/');
  await page.locator('#amount').fill('100');
  await page.locator('#swap-direction').click();
  await page.locator('[data-range="30"]').click();
  await page.getByRole('tab', { name: '歷史匯率', exact: true }).click();
  const original = await page.evaluate(() => ({
    timeOrigin: performance.timeOrigin,
    length: history.length,
  }));
  const dates = availableDates(ratesData.rates).slice(-7);
  for (const code of Object.keys(currencies)) {
    const info = currencyPage(code);
    const link = page.locator(`[data-quick-currency="${code}"]`);
    const href = new URL((await link.getAttribute('href'))!, page.url());
    expect(href.pathname).toBe(info.path);
    expect(href.searchParams.get('amount')).toBe('100');
    expect(href.searchParams.get('direction')).toBe('twd-to-foreign');
    await link.click();
    await expect(page).toHaveURL(
      (url) => url.pathname === info.path && !url.searchParams.has('currency'),
    );
    await expect(link).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('header h1')).toHaveText(info.heading);
    await expect(page).toHaveTitle(info.title);
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      'href',
      new RegExp(`${info.path}$`),
    );
    await expect(page.locator('meta[property="og:title"]')).toHaveAttribute(
      'content',
      info.title,
    );
    await expect(page.locator('#view-history')).toBeVisible();
    await expect(page.locator('.history-title')).toHaveText(
      `${currencies[code].name}歷史匯率`,
    );
    const row = page.locator('.rate-history tbody tr').first();
    for (const entry of rateEntries(ratesData.rates, code, dates.at(-1)!))
      await expect(row).toContainText(entry.rate.toFixed(6));
    for (const [index, range] of historyRanges(
      ratesData.rates,
      dates,
      code,
    ).entries())
      if (range.latest)
        await expect(
          page
            .locator('.range-item')
            .nth(index)
            .locator('.range-latest strong'),
        ).toHaveText(range.latest.rate.toFixed(6));
    await expect(page.locator('#amount')).toHaveValue('100');
    await expect(page.locator('#swap-direction')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(
      await page.evaluate(() => ({
        timeOrigin: performance.timeOrigin,
        length: history.length,
      })),
    ).toEqual(original);
  }
  await page.reload();
  await expect(page.locator('header h1')).toHaveText(
    currencyPage('SGD').heading,
  );
  await expect(page.locator('#amount')).toHaveValue('100');
});

test('shortcuts navigate to statically rendered currency pages without JavaScript', async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    baseURL,
  });
  try {
    const page = await context.newPage();
    await page.goto('/jpy/');
    await page.locator('[data-quick-currency="EUR"]').click();
    await expect(page).toHaveURL(/\/eur\/$/);
    await expect(page.locator('header h1')).toHaveText(
      currencyPage('EUR').heading,
    );
    await expect(page.locator('.history-title')).toHaveText('歐元歷史匯率');
    await expect(page.locator('#view-history')).toBeVisible();
    await expect(page.locator('.range-item')).toHaveCount(3);
    await page.locator('.view-tabs a[href="#view-method"]').click();
    await expect(page).toHaveURL(/\/eur\/#view-method$/);
    await expect(page.locator('#view-method')).toBeVisible();
    await expect(page.locator('#view-chart')).toBeVisible();
  } finally {
    await context.close();
  }
});
