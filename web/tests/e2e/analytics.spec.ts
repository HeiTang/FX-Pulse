import { expect, test, type Page } from '@playwright/test';

const commands = (page: Page) =>
  page.evaluate(() =>
    (window.dataLayer ?? []).map((entry) => Array.from(entry as IArguments)),
  );
const calculations = async (page: Page) =>
  (await commands(page)).filter((entry) => entry[1] === 'calculate');

test.beforeEach(async ({ page, baseURL }) => {
  // Serve the production hostname locally; never send test traffic to Google.
  await page.route('https://fx.purr.tw/**', async (route) => {
    const url = new URL(route.request().url());
    const response = await route.fetch({
      url: `${baseURL}${url.pathname}${url.search}`,
    });
    await route.fulfill({ response });
  });
  await page.route('https://www.googletagmanager.com/**', (route) =>
    route.fulfill({ contentType: 'text/javascript', body: '' }),
  );
  await page.route(/https:\/\/[^/]*google-analytics\.com\//, (route) =>
    route.abort(),
  );
});

test('landing pages record one view and strip trial amounts and unknown query values', async ({
  page,
}) => {
  for (const path of ['/', '/jpy/', '/usd/']) {
    await page.goto(
      `https://fx.purr.tw${path}?currency=USD&amount=12345&extra=private&utm_source=threads&utm_medium=social#results`,
    );
    await expect.poll(async () => (await commands(page)).length).toBe(3);
    const initial = await commands(page);
    expect(initial[1]).toEqual([
      'config',
      'G-4CXCX1QQP7',
      expect.objectContaining({
        send_page_view: false,
        page_location: `https://fx.purr.tw${path}?utm_source=threads&utm_medium=social`,
        allow_google_signals: false,
        allow_ad_personalization_signals: false,
      }),
    ]);
    expect(initial[2]).toEqual(['event', 'page_view']);
    await page.locator('#amount').fill('200');
    await page.locator('#amount').press('Enter');
    await expect.poll(async () => (await calculations(page)).length).toBe(1);
    expect(
      (await commands(page)).filter((entry) => entry[1] === 'page_view'),
    ).toHaveLength(1);
    expect(JSON.stringify(await commands(page))).not.toContain('12345');
    expect(JSON.stringify(await commands(page))).not.toContain('private');
  }
});

test('valid calculations debounce, deduplicate and omit amounts', async ({
  page,
}) => {
  await page.goto('https://fx.purr.tw/usd/');
  await expect.poll(async () => (await commands(page)).length).toBe(3);
  expect(await calculations(page)).toEqual([]);
  await page.locator('#amount').fill('100');
  await page.locator('#amount').fill('200');
  await page.locator('#amount').fill('300');
  await expect.poll(async () => (await calculations(page)).length).toBe(1);
  await page.locator('#amount').press('Tab');
  await page.locator('[data-quick-currency="USD"]').click();
  expect(await calculations(page)).toHaveLength(1);
  await page.locator('#amount').fill('invalid');
  await page.locator('#amount').press('Tab');
  expect(await calculations(page)).toHaveLength(1);
  await page.locator('#amount').fill('400');
  await page.locator('#amount').press('Enter');
  await expect.poll(async () => (await calculations(page)).length).toBe(2);
  await page.locator('#swap-direction').click();
  await expect.poll(async () => (await calculations(page)).length).toBe(3);
  await page.locator('[data-quick-currency="JPY"]').click();
  await expect.poll(async () => (await calculations(page)).length).toBe(4);
  expect((await calculations(page)).at(-1)).toEqual([
    'event',
    'calculate',
    {
      foreign_currency: 'JPY',
      conversion_direction: 'twd-to-foreign',
    },
  ]);
  for (const entry of await calculations(page))
    expect(Object.keys(entry[2] as object).sort()).toEqual([
      'conversion_direction',
      'foreign_currency',
    ]);
});

test('localhost does not load Google Analytics or queue events', async ({
  page,
}) => {
  let loadedGoogleTag = false;
  page.on('request', (request) => {
    if (request.url().includes('googletagmanager.com')) loadedGoogleTag = true;
  });
  await page.goto('/');
  await expect(page.locator('.result-row')).toHaveCount(3);
  await page.locator('#amount').fill('200');
  await page.locator('#amount').press('Enter');
  expect(await commands(page)).toEqual([]);
  expect(loadedGoogleTag).toBe(false);
});
