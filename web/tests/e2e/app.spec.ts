import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import ratesData from '../../src/data/rates.json' with { type: 'json' };
import {
  availableDates,
  rateEntries,
  type RateDays,
} from '../../src/lib/rates';

const days: RateDays = ratesData.rates;
const dates = availableDates(days);
const latest = dates.at(-1)!;
const comparable = dates.findLast(
  (date) => rateEntries(days, 'JPY', date).length === 3,
)!;
const fmt = new Intl.NumberFormat('zh-TW', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.result-row')).toHaveCount(3);
});

test('same-day amounts and differences match stored data across all currencies', async ({
  page,
}) => {
  await page.locator('#rate-date').evaluate((element, date) => {
    (element as HTMLInputElement).value = date;
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }, comparable);
  await page.locator('#amount').fill('10000');
  for (const code of ratesData.meta.currencies) {
    await page.locator('#currency').selectOption(code);
    const entries = rateEntries(days, code, comparable);
    const min = Math.min(...entries.map((entry) => entry.rate * 10000));
    for (const entry of entries) {
      const row = page.locator('.result-row').filter({
        has: page.locator('.result-source strong', { hasText: entry.src }),
      });
      await expect(row.locator('.result-total')).toHaveText(
        `NT$ ${fmt.format(entry.rate * 10000)}`,
      );
      if (Math.abs(entry.rate * 10000 - min) < 1e-7)
        await expect(row.locator('.result-difference')).toHaveText(
          '最低換算額',
        );
      else
        await expect(row.locator('.result-difference')).toHaveText(
          `+ NT$ ${fmt.format(entry.rate * 10000 - min)}`,
        );
    }
  }
});

test('invalid amounts show errors; valid inputs recover and precision follows currency', async ({
  page,
}) => {
  const amount = page.locator('#amount');
  for (const raw of ['', '0', '-1', 'abc', '1.5', '1,00', '1000000001']) {
    await amount.fill(raw);
    await expect(amount).toHaveAttribute('aria-invalid', 'true');
    await expect(page.locator('#amount-error')).not.toBeEmpty();
    await expect(page.locator('.result-total').first()).toHaveText('—');
  }
  await page.locator('#currency').selectOption('USD');
  await amount.fill('123.45');
  await expect(amount).toHaveAttribute('aria-invalid', 'false');
  await expect(page.locator('#amount-error')).toBeEmpty();
  await amount.fill('123.456');
  await expect(amount).toHaveAttribute('aria-invalid', 'true');
  await amount.fill('10000');
  await amount.blur();
  await expect(amount).toHaveValue('10,000');
});

test('calendar disables absent dates and supports keyboard selection and escape', async ({
  page,
}) => {
  await page.locator('#date-trigger').click();
  await expect(page.locator('#date-picker')).toBeVisible();
  await expect(page.locator('[data-month-step="1"]')).toBeDisabled();
  const nextDay = new Date(`${latest}T00:00:00Z`);
  nextDay.setUTCDate(nextDay.getUTCDate() + 1);
  const future = page.locator(
    `[data-date="${nextDay.toISOString().slice(0, 10)}"]`,
  );
  if (await future.count()) await expect(future).toBeDisabled();
  await page.keyboard.press('Escape');
  await expect(page.locator('#date-picker')).toBeHidden();
  await expect(page.locator('#date-trigger')).toBeFocused();
  await page.locator('#date-trigger').click();
  let month = latest.slice(0, 7);
  while (month !== dates[0].slice(0, 7)) {
    await page.locator('[data-month-step="-1"]').click();
    const date = new Date(`${month}-01T00:00:00Z`);
    date.setUTCMonth(date.getUTCMonth() - 1);
    month = date.toISOString().slice(0, 7);
  }
  await expect(page.locator('[data-month-step="-1"]')).toBeDisabled();
  const earlier = new Date(`${dates[0]}T00:00:00Z`);
  earlier.setUTCDate(earlier.getUTCDate() - 1);
  await expect(
    page.locator(`[data-date="${earlier.toISOString().slice(0, 10)}"]`),
  ).toBeDisabled();
  await page.locator(`[data-date="${dates[0]}"]`).click();
  await expect(page.locator('#date-display')).toHaveText(
    dates[0].replaceAll('-', '/'),
  );
  await expect(page.locator('#chart-placeholder')).toBeVisible();
});

test('rapid chart filters, currency shortcuts and overview retain the final selection', async ({
  page,
}) => {
  for (const code of ['USD', 'KRW', 'JPY'])
    await page.locator(`[data-quick-currency="${code}"]`).click();
  for (const range of ['all', '30', '7'])
    await page.locator(`[data-range="${range}"]`).click();
  for (const source of ['VISA', 'JCB', 'Mastercard', 'all'])
    await page.locator(`[data-source="${source}"]`).click();
  await expect(page.locator('#chart canvas')).toHaveCount(1);
  await expect(page.locator('#chart')).toHaveAttribute(
    'aria-label',
    /JPY.*VISA、Mastercard、JCB/,
  );
  await expect(page.locator('[data-range="7"]')).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.locator('summary').click();
  await page.locator('.currency-card[data-currency="EUR"]').click();
  await expect(page.locator('#currency')).toHaveValue('EUR');
  await expect(page.locator('#chart-title')).toHaveText('EUR / TWD');
});

test('missing sources are explicit and never replaced by rates from other dates', async ({
  page,
}) => {
  const entries = rateEntries(days, 'JPY', latest);
  for (const src of ['VISA', 'Mastercard', 'JCB']) {
    const row = page
      .locator('.result-row')
      .filter({ has: page.locator('.result-source strong', { hasText: src }) });
    if (!entries.some((entry) => entry.src === src)) {
      await expect(row.locator('.result-rate')).toHaveText('此日期無資料');
      await expect(row.locator('.result-total')).toHaveText('—');
    }
  }
  if (entries.length === 1) {
    await expect(page.locator('.best-badge')).toHaveCount(0);
    await expect(page.locator('#comparison-message')).toContainText('來源不足');
  }
  await expect(page.locator('.fine-print')).toContainText('JCB 為交叉匯率估算');
});

test('layout, assets and accessibility remain usable including large totals and calendar', async ({
  page,
}) => {
  const failures: string[] = [];
  page.on('pageerror', (error) => failures.push(error.message));
  page.on('response', (response) => {
    if (response.status() >= 400)
      failures.push(`${response.status()} ${response.url()}`);
  });
  await page.reload();
  await expect(page.locator('#chart canvas')).toHaveCount(1);
  await expect(page.locator('html')).toHaveCSS(
    'background-color',
    'rgb(17, 23, 32)',
  );
  await page.locator('#amount').fill('1000000000');
  await page.locator('#currency').selectOption('GBP');
  await page.locator('summary').click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  for (const image of await page.locator('img').all())
    expect(
      await image.evaluate(
        (image) => (image as HTMLImageElement).naturalWidth > 0,
      ),
    ).toBe(true);
  await page.locator('#date-trigger').click();
  const panel = (await page.locator('#date-picker').boundingBox())!;
  const viewport = page.viewportSize()!;
  expect(panel.x).toBeGreaterThanOrEqual(0);
  expect(panel.x + panel.width).toBeLessThanOrEqual(viewport.width);
  const audit = await new AxeBuilder({ page }).analyze();
  expect(
    audit.violations.map((violation) => ({
      id: violation.id,
      nodes: violation.nodes.map((node) => node.target),
    })),
  ).toEqual([]);
  expect(failures).toEqual([]);
});

test('direction switch preserves input and compares foreign budget amounts for every currency', async ({
  page,
}) => {
  await page.locator('#rate-date').evaluate((element, date) => {
    (element as HTMLInputElement).value = date;
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }, comparable);
  await page.locator('#swap-direction').click();
  await expect(page.locator('#amount')).toHaveValue('10,000');
  await page.locator('#amount').fill('123.45');
  await expect(page.locator('#amount')).toHaveAttribute(
    'aria-invalid',
    'false',
  );
  await expect(page.locator('#amount-code')).toHaveText('TWD');
  await expect(page.locator('#amount-label')).toHaveText('台幣預算');
  for (const code of ratesData.meta.currencies) {
    await page.locator('#currency').selectOption(code);
    const format = new Intl.NumberFormat('zh-TW', {
      style: 'currency',
      currency: code,
    });
    const digits = format.resolvedOptions().maximumFractionDigits;
    const amountFormat = new Intl.NumberFormat('zh-TW', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
    const entries = rateEntries(days, code, comparable);
    const best = Math.max(...entries.map((entry) => 123.45 / entry.rate));
    for (const entry of entries) {
      const row = page.locator('.result-row').filter({
        has: page.locator('.result-source strong', { hasText: entry.src }),
      });
      const total = 123.45 / entry.rate;
      await expect(row.locator('.result-total')).toHaveText(
        `${code} ${amountFormat.format(total)}`,
      );
      if (Math.abs(total - best) < 1e-7)
        await expect(row.locator('.result-difference')).toHaveText(
          '最高可換得金額',
        );
      else await expect(row.locator('.result-difference')).toContainText('−');
    }
    await expect(page.locator('#comparison-context')).toHaveText(
      `TWD → ${code}`,
    );
    await expect(page.locator('#chart-title')).toHaveText(`TWD / ${code}`);
  }
  await page.locator('#currency').selectOption('JPY');
  await page.locator('#swap-direction').press('Enter');
  await expect(page.locator('#swap-direction')).toBeFocused();
  await expect(page.locator('#swap-direction')).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await expect(page.locator('#amount')).toHaveValue('123.45');
  await expect(page.locator('#amount')).toHaveAttribute('aria-invalid', 'true');
  await page.locator('#swap-direction').press('Space');
  await expect(page.locator('#amount')).toHaveAttribute(
    'aria-invalid',
    'false',
  );
});

test('reverse mode handles missing data, rapid switches, overview and mobile accessibility', async ({
  page,
}) => {
  await page.locator('#swap-direction').click();
  for (const src of ['VISA', 'Mastercard', 'JCB']) {
    if (!days[latest]?.[src as keyof (typeof days)[string]]?.JPY) {
      const row = page.locator('.result-row').filter({
        has: page.locator('.result-source strong', { hasText: src }),
      });
      await expect(row.locator('.result-total')).toHaveText('—');
    }
  }
  for (const value of ['', '0', '-1', 'abc']) {
    await page.locator('#amount').fill(value);
    await expect(page.locator('#amount')).toHaveAttribute(
      'aria-invalid',
      'true',
    );
    await expect(page.locator('.best-badge')).toHaveCount(0);
  }
  await page.locator('#amount').fill('1000000000');
  for (const code of ['USD', 'JPY', 'KRW']) {
    await page.locator(`[data-quick-currency="${code}"]`).click();
    await page.locator('#swap-direction').click();
    await page.locator('#swap-direction').click();
  }
  await page.locator('[data-range="30"]').click();
  await page.locator('[data-source="JCB"]').click();
  await expect(page.locator('#chart canvas')).toHaveCount(1);
  await expect(page.locator('#chart')).toHaveAttribute(
    'aria-label',
    /TWD 對 KRW.*JCB/,
  );
  await expect(page.locator('#chart-note')).toContainText('1 TWD = KRW');
  const swap = (await page.locator('#swap-direction').boundingBox())!;
  expect(swap.width).toBeGreaterThanOrEqual(44);
  expect(swap.height).toBeGreaterThanOrEqual(44);
  const foreign = (await page.locator('.currency-field').boundingBox())!;
  const twd = (await page.locator('.route-destination').boundingBox())!;
  expect(twd.x).toBeLessThan(swap.x);
  expect(foreign.x).toBeGreaterThan(swap.x);
  await page.locator('summary').click();
  await expect(page.locator('#overview-hint')).toContainText('每 1 TWD');
  await page.locator('.currency-card[data-currency="USD"]').click();
  await expect(page.locator('#comparison-context')).toHaveText('TWD → USD');
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(page.locator('#conversion-note')).toContainText(
    '非銀行實際換匯報價',
  );
  const audit = await new AxeBuilder({ page }).analyze();
  expect(audit.violations.map((item) => item.id)).toEqual([]);
});
