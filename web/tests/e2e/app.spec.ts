import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import ratesData from '../../src/data/rates.json' with { type: 'json' };
import {
  availableDates,
  historyDates,
  periodComparison,
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

test('three-source comparison follows period, currency and cutoff', async ({
  page,
}) => {
  const panel = page.locator('.period-comparison');
  await expect(panel).not.toHaveAttribute('open', '');
  await panel.locator('summary').click();
  await expect(page.locator('#period-pair')).toHaveCount(0);
  for (const range of ['7', '30', 'all'] as const) {
    await page.locator(`[data-range="${range}"]`).click();
    for (const code of ['JPY', 'USD']) {
      await page.locator(`[data-quick-currency=${code}]`).click();
      const result = periodComparison(
        days,
        historyDates(dates, latest, range),
        code,
      );
      await expect(page.locator('#period-context')).toHaveText(
        `${range === 'all' ? '全部期間' : `近 ${range} 天`} · ${code} · 三家比較`,
      );
      await expect(page.locator('#period-count')).toHaveText(
        `${result.count} 天`,
      );
      for (const src of ['VISA', 'Mastercard', 'JCB'] as const)
        await expect(page.locator(`#period-${src.toLowerCase()}`)).toHaveText(
          `${result.bestDays[src]} 天`,
        );
      await expect(page.locator('#period-tied')).toHaveText(
        `${result.tied} 天`,
      );
      await expect(page.locator('#period-median')).toHaveText(
        result.median === null ? '—' : `約 NT$ ${fmt.format(result.median)}`,
      );
      await expect(page.locator('#period-maximum')).toHaveText(
        result.maximum === null ? '—' : `約 NT$ ${fmt.format(result.maximum)}`,
      );
    }
  }
  const median = await page.locator('#period-median').textContent();
  await page.locator('[data-source="JCB"]').click();
  await expect(page.locator('#period-median')).toHaveText(median!);
  await page.locator('#rate-date').evaluate((element, date) => {
    (element as HTMLInputElement).value = date;
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }, dates[0]);
  await expect(page.locator('#period-dates')).toHaveText(`截至 ${dates[0]}`);
  await expect(page.locator('#period-count')).toHaveText(
    `${periodComparison(days, [dates[0]], 'USD').count} 天`,
  );
  await page.goto('/?date=1900-01-01');
  await page.locator('.period-comparison summary').click();
  await expect(page.locator('#period-count')).toHaveText('0 天');
  await expect(page.locator('#period-median')).toHaveText('—');
  await expect(page.locator('#period-message')).toContainText('三家');
});

test('three-source comparison follows amount and direction with estimate labels', async ({
  page,
}) => {
  await page.locator('.period-comparison summary').click();
  await page.locator('[data-range="30"]').click();
  for (const amount of [20000, 30000]) {
    await page.locator('#amount').fill(String(amount));
    const result = periodComparison(
      days,
      historyDates(dates, latest, '30'),
      'JPY',
      amount,
    );
    await expect(page.locator('#period-median')).toHaveText(
      result.median === null ? '—' : `約 NT$ ${fmt.format(result.median)}`,
    );
    await expect(page.locator('#period-maximum')).toHaveText(
      result.maximum === null ? '—' : `約 NT$ ${fmt.format(result.maximum)}`,
    );
  }
  await expect(page.locator('#period-jcb-label')).toHaveText(
    'JCB 最低（估算）',
  );
  await expect(page.locator('#period-amount')).toHaveText(
    '換算 30,000 JPY → TWD',
  );
  await page.locator('#amount').fill('');
  await expect(page.locator('#period-median')).toHaveText('—');
  await expect(page.locator('#period-maximum')).toHaveText('—');
  await expect(page.locator('#period-amount')).toContainText('請輸入有效金額');
  await page.locator('#amount').fill('30000');
  await page.locator('#swap-direction').click();
  const reversed = periodComparison(
    days,
    historyDates(dates, latest, '30'),
    'JPY',
    30000,
    true,
  );
  const jpy = new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 0 });
  await expect(page.locator('#period-median')).toHaveText(
    reversed.median === null ? '—' : `約 JPY ${jpy.format(reversed.median)}`,
  );
  for (const src of ['VISA', 'Mastercard', 'JCB'] as const)
    await expect(page.locator(`#period-${src.toLowerCase()}`)).toHaveText(
      `${reversed.bestDays[src]} 天`,
    );
  await expect(page.locator('#period-mastercard-label')).toHaveText(
    'Mastercard 可換最多',
  );
  await expect(page.locator('#period-jcb-label')).toHaveText(
    'JCB 可換最多（估算）',
  );
  await expect(page.locator('#period-tied-label')).toHaveText('最多並列');
  await expect(page.locator('#period-amount')).toHaveText(
    '換算 30,000.00 TWD → JPY',
  );
  const audit = await new AxeBuilder({ page }).analyze();
  expect(audit.violations.map((item) => item.id)).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
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
    await page.locator(`[data-quick-currency=${code}]`).click();
    const entries = rateEntries(days, code, comparable);
    const min = Math.min(...entries.map((entry) => entry.rate * 10000));
    for (const entry of entries) {
      const row = page.locator('.result-row').filter({
        has: page.locator('.result-source strong', { hasText: entry.src }),
      });
      await expect(row.locator('.result-total')).toHaveText(
        `${entry.src === 'JCB' ? '約 ' : ''}NT$ ${fmt.format(entry.rate * 10000)}`,
      );
      if (Math.abs(entry.rate * 10000 - min) < 1e-7)
        await expect(row.locator('.result-difference')).toHaveText(
          entry.src === 'JCB' ? '最低參考換算額（估算）' : '最低換算額',
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
  await page.locator(`[data-quick-currency=${'USD'}]`).click();
  await amount.fill('123.45');
  await expect(amount).toHaveAttribute('aria-invalid', 'false');
  await expect(page.locator('#amount-error')).toBeEmpty();
  await amount.fill('123.456');
  await expect(amount).toHaveAttribute('aria-invalid', 'true');
  await amount.fill('10000');
  await amount.blur();
  await expect(amount).toHaveValue('10,000');
});

test('formatted amounts become plain digits while editing and stay valid after deletion', async ({
  page,
}) => {
  const amount = page.locator('#amount');
  await amount.fill('1000');
  await amount.blur();
  await expect(amount).toHaveValue('1,000');
  await amount.focus();
  await expect(amount).toHaveValue('1000');
  await amount.press('ArrowRight');
  await amount.press('Backspace');
  await expect(amount).toHaveValue('100');
  await expect(amount).toHaveAttribute('aria-invalid', 'false');
  await expect(page.locator('#amount-error')).toBeEmpty();
  await expect(page.locator('#period-amount')).toHaveText('換算 100 JPY → TWD');
  await amount.blur();
  await expect(amount).toHaveValue('100');

  await page.locator(`[data-quick-currency=${'USD'}]`).click();
  await amount.fill('1234.56');
  await amount.blur();
  await expect(amount).toHaveValue('1,234.56');
  await amount.focus();
  await expect(amount).toHaveValue('1234.56');
  await amount.press('ArrowRight');
  await amount.press('Backspace');
  await expect(amount).toHaveValue('1234.5');
  await expect(amount).toHaveAttribute('aria-invalid', 'false');
  await amount.blur();
  await expect(amount).toHaveValue('1,234.5');
});

test('currency shortcuts replace duplicate controls and show same-day reference rates in both directions', async ({
  page,
}) => {
  await expect(page.locator('[data-quick-currency]')).toHaveCount(
    ratesData.meta.currencies.length,
  );
  await expect(page.locator('#overview-grid, .select-wrap')).toHaveCount(0);
  for (const date of [latest, comparable]) {
    await page.locator('#rate-date').evaluate((element, value) => {
      (element as HTMLInputElement).value = value;
      element.dispatchEvent(new Event('change', { bubbles: true }));
    }, date);
    for (const reverse of [false, true]) {
      for (const code of ratesData.meta.currencies) {
        const candidates = rateEntries(days, code, date, reverse).sort(
          (a, b) => (reverse ? b.rate - a.rate : a.rate - b.rate),
        );
        const best = candidates[0];
        const button = page.locator(`[data-quick-currency="${code}"]`);
        const rate = best
          ? new Intl.NumberFormat('zh-TW', {
              maximumSignificantDigits: 4,
            }).format(best.rate)
          : '';
        await expect(button.locator('[data-shortcut-rate]')).toHaveText(
          best ? `${best.src === 'JCB' ? '約 ' : ''}${rate}` : '—',
        );
        await expect(button.locator('[data-shortcut-source]')).toHaveCount(0);
        await expect(button.locator('.shortcut-heading strong')).toHaveText(
          code,
        );
        await expect(button.locator('.shortcut-heading')).toHaveCSS(
          'display',
          'flex',
        );
      }
      await page.locator('#swap-direction').click();
    }
  }
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

test('rapid chart filters, currency shortcuts retain the final selection', async ({
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
  await page.locator('[data-quick-currency="EUR"]').click();
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
      await expect(row.locator('.result-rate')).toContainText('此日期無資料');
      await expect(row.locator('.result-total')).toHaveText('—');
    }
  }
  if (entries.length === 1) {
    await expect(page.locator('.best-badge')).toHaveCount(0);
    await expect(page.locator('#comparison-message')).toContainText('來源不足');
  }
  await expect(page.locator('#conversion-note')).toContainText(
    'JCB 為交叉匯率估算',
  );
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
  await page.locator(`[data-quick-currency=${'GBP'}]`).click();
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
    await page.locator(`[data-quick-currency=${code}]`).click();
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
        `${entry.src === 'JCB' ? '約 ' : ''}${code} ${amountFormat.format(total)}`,
      );
      if (Math.abs(total - best) < 1e-7)
        await expect(row.locator('.result-difference')).toHaveText(
          entry.src === 'JCB' ? '最高參考可換得金額（估算）' : '最高可換得金額',
        );
      else await expect(row.locator('.result-difference')).toContainText('−');
    }
    await expect(page.locator('#comparison-context')).toHaveText(
      `TWD → ${code}`,
    );
    await expect(page.locator('#chart-title')).toHaveText(`TWD / ${code}`);
  }
  await page.locator(`[data-quick-currency=${'JPY'}]`).click();
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

test('reverse mode handles missing data, rapid switches, shortcuts and mobile accessibility', async ({
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
  await expect(page.locator('#shortcut-hint')).toContainText('每 1 TWD');
  await page.locator('[data-quick-currency="USD"]').click();
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
