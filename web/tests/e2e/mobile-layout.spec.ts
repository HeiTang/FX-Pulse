import { devices, expect, test, type Page } from '@playwright/test';
import ratesData from '../../src/data/rates.json' with { type: 'json' };
import { availableDates } from '../../src/lib/rates';
import { resultRows } from '../../src/lib/results';

declare global {
  interface Window {
    queryWrites: number;
  }
}

const latest = availableDates(ratesData.rates).at(-1)!;

const phones = [
  'iPhone SE',
  'iPhone 16e',
  'iPhone 16',
  'iPhone 17',
  'iPhone 17 Pro Max',
  'Galaxy S24',
  'Pixel 9',
  'Pixel 9 Pro',
  'Pixel 9 Pro XL',
];
const currencies = ['JPY', 'USD', 'EUR', 'GBP', 'HKD', 'AUD', 'KRW', 'SGD'];

async function inspectLayout(page: Page) {
  // Read final geometry after ResizeObserver and the browser's layout pass.
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  return page.evaluate(() => {
    const results = document.querySelector<HTMLElement>('#results')!;
    const stacked = results.classList.contains('is-stacked');
    return {
      width: innerWidth,
      overflow: document.documentElement.scrollWidth > innerWidth,
      stacked,
      rows: [...results.querySelectorAll<HTMLElement>('.result-headline')].map(
        (headline) => {
          const source = headline.querySelector<HTMLElement>('.result-source')!;
          const total = headline.querySelector<HTMLElement>('.result-total')!;
          const number = total.querySelector('strong')!;
          const a = source.getBoundingClientRect();
          const b = total.getBoundingClientRect();
          const range = document.createRange();
          range.selectNodeContents(number);
          return {
            source: source.querySelector('strong')!.textContent,
            total: total.textContent,
            card: getComputedStyle(headline).display === 'flex',
            fontSize: getComputedStyle(number).fontSize,
            fits: headline.scrollWidth <= headline.clientWidth,
            below: b.top >= a.bottom,
            beside: b.left >= a.right && b.top < a.bottom && a.top < b.bottom,
            lines: range.getClientRects().length,
          };
        },
      ),
      controlsFit: [
        '#amount',
        '#date-trigger',
        '.comparison-panel',
        '.history-panel',
      ].every((selector) => {
        const box = document.querySelector(selector)!.getBoundingClientRect();
        return box.left >= -1 && box.right <= innerWidth + 1;
      }),
    };
  });
}

async function expectPhoneLayout(page: Page) {
  const state = await inspectLayout(page);
  expect(state.overflow, JSON.stringify(state)).toBe(false);
  expect(state.controlsFit, JSON.stringify(state)).toBe(true);
  expect(state.rows).toHaveLength(3);
  for (const row of state.rows) {
    expect(row.card, JSON.stringify(state)).toBe(true);
    expect(row.fontSize).toBe('26px');
    expect(row.fits, JSON.stringify(state)).toBe(true);
    expect(state.stacked ? row.below : row.beside, JSON.stringify(state)).toBe(
      true,
    );
    if (!state.stacked) expect(row.lines, JSON.stringify(state)).toBe(1);
  }
  return state;
}

for (const name of phones) {
  test.describe(name, () => {
    test.use({
      deviceScaleFactor: devices[name].deviceScaleFactor,
      userAgent: devices[name].userAgent,
      reducedMotion: 'reduce',
    });
    test('portrait, landscape, amounts and currencies', async ({
      page,
    }, testInfo) => {
      test.setTimeout(120000);
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));
      const portrait = devices[name].viewport;
      const landscape = devices[`${name} landscape`].viewport;
      await page.setViewportSize(portrait);
      await page.goto('/?currency=EUR&amount=10000');
      await expect(page.locator('#comparison-context')).toHaveText('EUR → TWD');
      const observations = [];
      for (const viewport of [portrait, landscape, portrait]) {
        await page.setViewportSize(viewport);
        for (const currency of currencies) {
          await page.locator(`[data-quick-currency="${currency}"]`).click();
          for (const reverse of [false, true]) {
            if (
              (await page
                .locator('#swap-direction')
                .getAttribute('aria-pressed')) !== String(reverse)
            )
              await page.locator('#swap-direction').click();
            for (const amount of ['10000', '1000000000']) {
              await page.locator('#amount').fill(amount);
              const state = await expectPhoneLayout(page);
              expect(state.rows.map((row) => row.total)).toEqual(
                resultRows(
                  ratesData.rates,
                  currency,
                  latest,
                  Number(amount),
                  reverse,
                ).map((row) => row.totalText),
              );
              observations.push({
                viewport,
                currency,
                reverse,
                amount,
                stacked: state.stacked,
              });
            }
          }
        }
        await page.locator('.period-comparison summary').click();
        await expectPhoneLayout(page);
        await page.locator('#date-trigger').click();
        const calendar = (await page.locator('#date-picker').boundingBox())!;
        expect(calendar.x).toBeGreaterThanOrEqual(0);
        expect(calendar.x + calendar.width).toBeLessThanOrEqual(viewport.width);
        await page.keyboard.press('Escape');
      }
      expect(errors).toEqual([]);
      await testInfo.attach('mobile-layout-matrix', {
        body: JSON.stringify(observations),
        contentType: 'application/json',
      });
    });
  });
}

test('breakpoint sweep and viewport height changes preserve synchronized rows', async ({
  page,
}) => {
  await page.goto('/?currency=EUR&amount=10000');
  await expect(page.locator('#comparison-context')).toHaveText('EUR → TWD');
  for (const width of [
    320, 360, 375, 384, 390, 393, 402, 411, 412, 414, 427, 430, 432, 440, 448,
    460, 480, 600, 680, 739, 740, 759, 760, 761, 768, 780, 812, 844, 852, 874,
    900, 932, 945, 956, 997, 1024, 1055, 1056,
  ]) {
    for (const height of [320, 844]) {
      await page.setViewportSize({ width, height });
      await expectPhoneLayout(page);
    }
  }
  await page.setViewportSize({ width: 1057, height: 844 });
  await expect(page.locator('.table-head')).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(page.locator('.table-head')).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expectPhoneLayout(page);
});

test('rapid amount edits keep results and the final shared URL current', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(() => {
    const state = window;
    state.queryWrites = 0;
    const replace = history.replaceState.bind(history);
    history.replaceState = (...args) => {
      state.queryWrites++;
      replace(...args);
    };
  });
  await page.goto('/?currency=EUR&amount=10000');
  await expect(page.locator('#comparison-context')).toHaveText('EUR → TWD');
  await page.locator('#amount').evaluate((input) => {
    for (let amount = 1; amount <= 150; amount++) {
      (input as HTMLInputElement).value = String(amount);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  });
  await expect(page).toHaveURL(
    (url) => url.searchParams.get('amount') === '150',
  );
  await expect(page.locator('.result-total strong')).toHaveText(
    resultRows(ratesData.rates, 'EUR', latest, 150).map((row) => row.totalText),
  );
  expect(await page.evaluate(() => window.queryWrites)).toBeLessThan(20);
  expect(errors).toEqual([]);
});
