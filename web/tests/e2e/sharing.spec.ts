import { expect, test } from '@playwright/test';
import ratesData from '../../src/data/rates.json' with { type: 'json' };
import { availableDates } from '../../src/lib/rates';

const dates = availableDates(ratesData.rates);
const latest = dates.at(-1)!;

for (const direction of ['foreign-to-twd', 'twd-to-foreign']) {
  test(`shared ${direction} query restores all conditions in the address bar`, async ({
    page,
  }) => {
    await page.goto(`/?currency=JPY&amount=12345&direction=${direction}`);
    await expect(page.locator('#amount')).toHaveValue('12345');
    await expect(page.locator('#currency')).toHaveValue('JPY');
    await expect(page.locator('#date-display')).toHaveText(
      latest.replaceAll('-', '/'),
    );
    await expect(page.locator('#swap-direction')).toHaveAttribute(
      'aria-pressed',
      String(direction === 'twd-to-foreign'),
    );
    await expect(page.locator('#comparison-context')).toHaveText(
      direction === 'twd-to-foreign' ? 'TWD → JPY' : 'JPY → TWD',
    );
    const copied = page.url();
    const url = new URL(copied);
    expect(Object.fromEntries(url.searchParams)).toEqual({
      currency: 'JPY',
      amount: '12345',
      direction,
    });
    await page.goto(copied!);
    await expect(page.locator('#comparison-context')).toHaveText(
      direction === 'twd-to-foreign' ? 'TWD → JPY' : 'JPY → TWD',
    );
    await expect(page.locator('.result-meta')).toHaveCount(0);
    await expect(page.locator('#share-query')).toHaveCount(0);
    const jcb = page.locator('.result-row').filter({
      has: page.locator('.result-source strong', { hasText: 'JCB' }),
    });
    await expect(jcb.locator('.result-total')).toContainText('約 ');
    await expect(jcb.locator('.source-estimate')).toHaveText('交叉匯率估算');
    await expect(jcb.locator('.source-estimate')).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}

test('edits replace URL conditions without navigation or history entries and retain invalid amounts', async ({
  page,
}) => {
  await page.goto(`/?currency=USD&amount=100.5&extra=keep#results`);
  const before = await page.evaluate(() => {
    history.replaceState({ marker: 'preserved' }, '', location.href);
    return { length: history.length, timeOrigin: performance.timeOrigin };
  });
  await page.locator(`[data-quick-currency=${'EUR'}]`).click();
  await page.locator('#amount').fill('200.25');
  await page.locator('#swap-direction').click();
  await page.locator('#rate-date').evaluate((element, date) => {
    (element as HTMLInputElement).value = date;
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }, dates[0]);
  let url = new URL(page.url());
  expect(Object.fromEntries(url.searchParams)).toEqual({
    currency: 'EUR',
    amount: '200.25',
    direction: 'twd-to-foreign',
    extra: 'keep',
  });
  expect(url.hash).toBe('#results');
  expect(
    await page.evaluate(() => ({
      length: history.length,
      timeOrigin: performance.timeOrigin,
    })),
  ).toEqual(before);
  expect(await page.evaluate(() => history.state)).toEqual({
    marker: 'preserved',
  });
  await page.locator('#amount').fill('1,00');
  url = new URL(page.url());
  expect(url.searchParams.get('amount')).toBe('1,00');
  await page.reload();
  await expect(page.locator('#amount')).toHaveValue('1,00');
  await expect(page.locator('#amount')).toHaveAttribute('aria-invalid', 'true');
  await page.locator('#amount').fill('');
  expect(new URL(page.url()).searchParams.get('amount')).toBe('');
  await page.reload();
  await expect(page.locator('#amount')).toHaveValue('');
  await expect(page.locator('#amount')).toHaveAttribute('aria-invalid', 'true');
});

for (const date of [dates[0], '2099-01-03', '2026-02-30']) {
  test(`legacy date ${date} is ignored and removed`, async ({ page }) => {
    await page.goto(`/?currency=JPY&amount=10000&date=${date}`);
    await expect(page.locator('#rate-date')).toHaveValue(latest);
    await expect(page.locator('#date-display')).toHaveText(
      latest.replaceAll('-', '/'),
    );
    await expect(page.locator('#date-error')).toBeEmpty();
    expect(new URL(page.url()).searchParams.has('date')).toBe(false);
  });
}

test('calendar selection stays local and reload uses latest data', async ({
  page,
}) => {
  await page.goto('/?currency=USD&amount=200');
  await expect(page.locator('#currency')).toHaveValue('USD');
  await page.locator('#rate-date').evaluate((element, date) => {
    (element as HTMLInputElement).value = date;
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }, dates[0]);
  await expect(page.locator('#rate-date')).toHaveValue(dates[0]);
  expect(new URL(page.url()).searchParams.has('date')).toBe(false);
  await page.reload();
  await expect(page.locator('#rate-date')).toHaveValue(latest);
  await expect(page.locator('#currency')).toHaveValue('USD');
  await expect(page.locator('#amount')).toHaveValue('200');
});

test('invalid query parameters show errors and omitted values use defaults', async ({
  page,
}) => {
  await page.goto(
    '/?currency=XXX&amount=abc&date=2026-02-30&direction=invalid',
  );
  await expect(page.locator('#currency')).toHaveValue('JPY');
  await expect(page.locator('#amount')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.locator('#amount-error')).not.toBeEmpty();
  await expect(page.locator('#date-error')).toBeEmpty();
  await expect(page.locator('#query-message')).toContainText('幣別不支援');
  await expect(page.locator('#query-message')).toContainText('換算方向無效');
  await expect(page.locator('#swap-direction')).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await page.goto('/');
  await expect(page.locator('#amount')).toHaveValue('10,000');
  await expect(page.locator('#rate-date')).toHaveValue(dates.at(-1)!);
  await expect(page.locator('#query-message')).toBeEmpty();
  await expect(page.locator('.site-footer')).toContainText('更新時間');
});
