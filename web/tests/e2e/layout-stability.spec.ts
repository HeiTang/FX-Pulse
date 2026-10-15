import { test, expect } from '@playwright/test';

test('initial results preserve layout while the app script is delayed', async ({
  page,
}, testInfo) => {
  await page.addInitScript(() => {
    const state = window as Window & { layoutShiftScore: number };
    state.layoutShiftScore = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as PerformanceEntry & {
          hadRecentInput: boolean;
          value: number;
        };
        if (!shift.hadRecentInput) state.layoutShiftScore += shift.value;
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
  await page.goto('/', { waitUntil: 'commit' });
  const measure = async () => {
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    );
    return page.evaluate(() =>
      Object.fromEntries(
        ['.workspace', '.comparison', '#results', '.history'].map(
          (selector) => {
            const rect = document
              .querySelector(selector)!
              .getBoundingClientRect();
            return [selector, { y: rect.y, height: rect.height }];
          },
        ),
      ),
    );
  };
  try {
    await expect(page.locator('.result-row')).toHaveCount(3);
    const totals = await page.locator('.result-total strong').allTextContents();
    const before = await measure();
    expect(before['#results'].height).toBeGreaterThan(0);
    release();
    await page.waitForLoadState('networkidle');
    const after = await measure();
    expect(
      await page.locator('.result-total strong').allTextContents(),
    ).toEqual(totals);
    for (const selector of Object.keys(before)) {
      expect(Math.abs(after[selector].y - before[selector].y)).toBeLessThan(1);
      expect(
        Math.abs(after[selector].height - before[selector].height),
      ).toBeLessThan(1);
    }
    const cls = await page.evaluate(
      () => (window as Window & { layoutShiftScore: number }).layoutShiftScore,
    );
    expect(cls).toBe(0);
    await testInfo.attach('initial-layout', {
      body: JSON.stringify({ before, after, cls }),
      contentType: 'application/json',
    });
  } finally {
    release();
  }
});
