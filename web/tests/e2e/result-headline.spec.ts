import { expect, test, type Page } from '@playwright/test';

async function expectLayout(page: Page, stacked: boolean) {
  await expect(page.locator('#results')).toHaveClass(
    stacked ? /is-stacked/ : /^results$/,
  );
  for (const headline of await page.locator('.result-headline').all()) {
    const source = (await headline.locator('.result-source').boundingBox())!;
    const total = (await headline.locator('.result-total').boundingBox())!;
    const bounds = (await headline.boundingBox())!;
    if (stacked) {
      expect(total.y).toBeGreaterThanOrEqual(source.y + source.height);
    } else {
      expect(total.y).toBeLessThan(source.y + source.height);
      expect(source.y).toBeLessThan(total.y + total.height);
      expect(total.x).toBeGreaterThanOrEqual(source.x + source.width);
    }
    expect(total.x).toBeGreaterThanOrEqual(bounds.x);
    expect(total.x + total.width).toBeCloseTo(bounds.x + bounds.width, 0);
    await expect(headline.locator('.result-total strong')).toHaveCSS(
      'font-size',
      '26px',
    );
    expect(
      await headline.evaluate(
        (element) => element.scrollWidth <= element.clientWidth,
      ),
    ).toBe(true);
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
}

for (const amount of ['10,000', '1000000000']) {
  test(`all mobile result headlines share layout for EUR ${amount}`, async ({
    page,
  }) => {
    const width = page.viewportSize()!.width;
    test.skip(width > 760, 'Mobile headline layout');
    await page.goto(
      `/?${new URLSearchParams({ currency: 'EUR', amount, direction: 'foreign-to-twd' })}`,
    );
    await expect(page.locator('#comparison-context')).toHaveText('EUR → TWD');
    await expect(page.locator('.result-row')).toHaveCount(3);
    await expectLayout(page, width < 680);
    if (amount === '10,000') {
      for (const total of await page.locator('.result-total strong').all()) {
        expect(
          await total.evaluate((element) => {
            const range = document.createRange();
            range.selectNodeContents(element);
            return range.getClientRects().length;
          }),
        ).toBe(1);
      }
    }
  });
}

test('headlines recalculate together after resize and amount changes', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?currency=EUR&amount=10000');
  await expect(page.locator('#comparison-context')).toHaveText('EUR → TWD');
  await expectLayout(page, true);
  await page.setViewportSize({ width: 680, height: 844 });
  await expectLayout(page, false);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectLayout(page, true);
  await page.locator('#amount').fill('1');
  await expectLayout(page, false);
  await page.locator('#amount').fill('10000');
  await expectLayout(page, true);
});
