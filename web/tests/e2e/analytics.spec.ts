import { expect, test, type Page } from '@playwright/test';
import astroConfig, { gaMeasurementId } from '../../astro.config.mjs';

const site = new URL('/', astroConfig.site).origin;

const commands = (page: Page) =>
  page.evaluate(() =>
    (window.dataLayer ?? []).map((entry) => Array.from(entry as IArguments)),
  );
const calculations = async (page: Page) =>
  (await commands(page)).filter((entry) => entry[1] === 'calculate');
const tabViews = async (page: Page) =>
  (await commands(page)).filter((entry) => entry[1] === 'rate_tab_view');
const chartFilters = async (page: Page) =>
  (await commands(page)).filter((entry) => entry[1] === 'chart_filter_change');
const pageViews = async (page: Page) =>
  (await commands(page)).filter((entry) => entry[1] === 'page_view');
const settleVisibility = (page: Page) =>
  page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );

test.beforeEach(async ({ page, baseURL }) => {
  // Serve the production hostname locally; never send test traffic to Google.
  await page.route(`${site}/**`, async (route) => {
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
      `${site}${path}?currency=USD&amount=12345&extra=private&utm_source=threads&utm_medium=social#results`,
    );
    await expect.poll(async () => (await pageViews(page)).length).toBe(1);
    const initial = await commands(page);
    expect(initial[1]).toEqual([
      'config',
      gaMeasurementId,
      expect.objectContaining({
        send_page_view: false,
        page_location: `${site}${path}?utm_source=threads&utm_medium=social`,
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
  await page.goto(`${site}/usd/`);
  await expect.poll(async () => (await pageViews(page)).length).toBe(1);
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

test('Google tag waits for idle while views and calculations stay queued', async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.requestIdleCallback = (callback, options) => {
      if (options?.timeout !== 1000) throw new Error('Missing idle timeout');
      window.addEventListener(
        'test:idle',
        () => callback({ didTimeout: false, timeRemaining: () => 50 }),
        { once: true },
      );
      return 1;
    };
  });
  const requests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('googletagmanager.com'))
      requests.push(request.url());
  });
  await page.goto(`${site}/jpy/`);
  await expect.poll(async () => (await pageViews(page)).length).toBe(1);
  expect(requests).toHaveLength(0);
  await page.locator('#amount').fill('200');
  await page.locator('#amount').press('Enter');
  await expect.poll(async () => (await calculations(page)).length).toBe(1);
  await page.evaluate(() => window.dispatchEvent(new Event('test:idle')));
  await expect.poll(() => requests.length).toBe(1);
  expect(
    (await commands(page)).filter((entry) => entry[1] === 'page_view'),
  ).toHaveLength(1);
  expect(await calculations(page)).toHaveLength(1);
});

test('Google tag loads when requestIdleCallback is unavailable', async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'requestIdleCallback', { value: undefined });
  });
  const tag = page.waitForRequest('https://www.googletagmanager.com/**');
  await page.goto(`${site}/usd/`);
  await tag;
  expect(
    (await commands(page)).filter((entry) => entry[1] === 'page_view'),
  ).toHaveLength(1);
});

test('tabs count only their first actual view, with the current currency', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 600 });
  await page.goto(`${site}/jpy/`);
  await page.waitForLoadState('networkidle');
  expect(await tabViews(page)).toEqual([]);
  // Selecting an offscreen panel alone is not a view.
  await page
    .locator('#tab-method')
    .evaluate((el) => (el as HTMLElement).click());
  await settleVisibility(page);
  expect(await tabViews(page)).toEqual([]);
  await page
    .locator('#tab-chart')
    .evaluate((el) => (el as HTMLElement).click());
  await page.locator('#view-chart').scrollIntoViewIfNeeded();
  await expect.poll(async () => (await tabViews(page)).length).toBe(1);
  expect((await tabViews(page))[0]).toEqual([
    'event',
    'rate_tab_view',
    { tab_name: 'chart', foreign_currency: 'JPY' },
  ]);
  await page.locator('[data-quick-currency="USD"]').click();
  await page.locator('#tab-history').click();
  await page.locator('#view-history').scrollIntoViewIfNeeded();
  await expect.poll(async () => (await tabViews(page)).length).toBe(2);
  await page.locator('#tab-history').press('End');
  await page.locator('#view-method').scrollIntoViewIfNeeded();
  await expect.poll(async () => (await tabViews(page)).length).toBe(3);
  expect((await tabViews(page)).slice(1)).toEqual([
    [
      'event',
      'rate_tab_view',
      { tab_name: 'history', foreign_currency: 'USD' },
    ],
    ['event', 'rate_tab_view', { tab_name: 'method', foreign_currency: 'USD' }],
  ]);
  await page.locator('#tab-method').press('Home');
  await page.locator('#view-chart').scrollIntoViewIfNeeded();
  await settleVisibility(page);
  expect(await tabViews(page)).toHaveLength(3);
  expect(await pageViews(page)).toHaveLength(1);
  await page.reload();
  await page.locator('#view-chart').scrollIntoViewIfNeeded();
  await expect.poll(async () => (await tabViews(page)).length).toBe(1);
});

test('a visible panel in a background document counts only after returning', async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });
  });
  await page.goto(`${site}/jpy/`);
  await page.locator('#tab-method').click();
  await page.locator('#view-method').scrollIntoViewIfNeeded();
  await settleVisibility(page);
  expect(await tabViews(page)).toEqual([]);
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'visible' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect
    .poll(() => tabViews(page))
    .toEqual([
      [
        'event',
        'rate_tab_view',
        { tab_name: 'method', foreign_currency: 'JPY' },
      ],
    ]);
});

test('chart filters record changes once, including returning to an earlier value', async ({
  page,
}) => {
  await page.goto(`${site}/jpy/`);
  await page.locator('[data-range="7"]').click();
  await page.locator('[data-source="all"]').click();
  expect(await chartFilters(page)).toEqual([]);
  await page.locator('[data-range="30"]').click();
  await page.locator('[data-range="30"]').click();
  await page.locator('[data-range="all"]').click();
  await page.locator('[data-source="VISA"]').click();
  await page.locator('[data-source="VISA"]').click();
  await page.locator('[data-source="JCB"]').click();
  await page.locator('[data-source="all"]').click();
  expect(await chartFilters(page)).toEqual([
    [
      'event',
      'chart_filter_change',
      { filter_type: 'range', filter_value: '30', foreign_currency: 'JPY' },
    ],
    [
      'event',
      'chart_filter_change',
      { filter_type: 'range', filter_value: 'all', foreign_currency: 'JPY' },
    ],
    [
      'event',
      'chart_filter_change',
      { filter_type: 'source', filter_value: 'VISA', foreign_currency: 'JPY' },
    ],
    [
      'event',
      'chart_filter_change',
      { filter_type: 'source', filter_value: 'JCB', foreign_currency: 'JPY' },
    ],
    [
      'event',
      'chart_filter_change',
      { filter_type: 'source', filter_value: 'all', foreign_currency: 'JPY' },
    ],
  ]);
  await page.locator('[data-quick-currency="USD"]').click();
  await page.locator('[data-range="7"]').click();
  await page.locator('[data-range="30"]').click();
  expect((await chartFilters(page)).slice(5)).toEqual([
    [
      'event',
      'chart_filter_change',
      { filter_type: 'range', filter_value: '7', foreign_currency: 'USD' },
    ],
    [
      'event',
      'chart_filter_change',
      { filter_type: 'range', filter_value: '30', foreign_currency: 'USD' },
    ],
  ]);
  expect(await pageViews(page)).toHaveLength(1);
});
