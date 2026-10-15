import { expect, test } from '@playwright/test';
import ratesData from '../../src/data/rates.json' with { type: 'json' };
import {
  availableDates,
  fractionDigits,
  rateEntries,
} from '../../src/lib/rates';

const latest = availableDates(ratesData.rates).at(-1)!;
const scenarios = [
  { currency: 'USD', amount: '1234.56', direction: 'foreign-to-twd' },
  { currency: 'EUR', amount: '1000000000', direction: 'foreign-to-twd' },
  { currency: 'KRW', amount: '1000000', direction: 'foreign-to-twd' },
  { currency: 'JPY', amount: '30000', direction: 'twd-to-foreign' },
  { currency: 'KRW', amount: '1000000000', direction: 'twd-to-foreign' },
  { currency: 'USD', amount: '12345.67', direction: 'twd-to-foreign' },
];

for (const scenario of scenarios) {
  test(`shared layout ${scenario.currency} ${scenario.amount} ${scenario.direction}`, async ({
    page,
  }, testInfo) => {
    await page.addInitScript(() => {
      window.layoutShiftScore = 0;
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const shift = entry as PerformanceEntry & {
            hadRecentInput: boolean;
            value: number;
          };
          if (!shift.hadRecentInput) window.layoutShiftScore += shift.value;
        }
      }).observe({ type: 'layout-shift', buffered: true });
    });
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route('**/_astro/index*.js', async (route) => {
      await gate;
      await route.continue();
    });
    await page.goto(`/?${new URLSearchParams(scenario)}`, {
      waitUntil: 'commit',
    });
    try {
      await expect(page.locator('.result-row')).toHaveCount(3);
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
      );
      release();
      await page.waitForLoadState('networkidle');
      const reversed = scenario.direction === 'twd-to-foreign';
      await expect(page.locator('#comparison-context')).toHaveText(
        reversed ? `TWD → ${scenario.currency}` : `${scenario.currency} → TWD`,
      );
      await expect(page.locator('#currency')).toHaveValue(scenario.currency);
      await expect(page.locator('#amount')).toHaveValue(scenario.amount);
      await expect(page.locator('#swap-direction')).toHaveAttribute(
        'aria-pressed',
        String(reversed),
      );
      const to = reversed ? scenario.currency : 'TWD';
      const format = new Intl.NumberFormat('zh-TW', {
        minimumFractionDigits: fractionDigits(to),
        maximumFractionDigits: fractionDigits(to),
      });
      for (const entry of rateEntries(
        ratesData.rates,
        scenario.currency,
        latest,
        reversed,
      )) {
        const row = page.locator('.result-row').filter({
          has: page.locator('.result-source strong', { hasText: entry.src }),
        });
        await expect(row.locator('.result-total')).toHaveText(
          `${entry.src === 'JCB' ? '約 ' : ''}${to === 'TWD' ? 'NT$' : to} ${format.format(Number(scenario.amount) * entry.rate)}`,
        );
      }
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      const cls = await page.evaluate(() => window.layoutShiftScore);
      expect(cls).toBe(0);
      await testInfo.attach('shared-layout', {
        body: JSON.stringify({
          viewport: testInfo.project.name,
          ...scenario,
          cls,
        }),
        contentType: 'application/json',
      });
    } finally {
      release();
    }
  });
}
