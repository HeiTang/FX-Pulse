import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { expect, test } from '@playwright/test';

test.use({
  viewport: { width: 1350, height: 940 },
  deviceScaleFactor: 1,
  isMobile: false,
  launchOptions: {
    // Playwright otherwise hides the classic scrollbar that caused the PSI shift.
    ignoreDefaultArgs: ['--hide-scrollbars'],
    args: ['--disable-features=OverlayScrollbar,FluentOverlayScrollbar'],
  },
});

let server: Server | undefined;
let origin: string;
let release: (() => void) | undefined;

test.beforeAll(async ({ baseURL }) => {
  const html = await (await fetch(baseURL!)).text();
  const split = html.indexOf('<section class="comparison"');
  expect(split).toBeGreaterThan(0);
  server = createServer(async (request, response) => {
    if (request.url?.startsWith('/?')) {
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      response.write(
        html
          .slice(0, split)
          .replace(
            '</head>',
            process.platform === 'linux'
              ? '<style>::-webkit-scrollbar{width:15px;height:15px}</style></head>'
              : '</head>',
          ),
      );
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      response.end(html.slice(split));
    } else {
      const upstream = await fetch(new URL(request.url!, baseURL));
      response.writeHead(
        upstream.status,
        Object.fromEntries(
          [...upstream.headers].filter(
            ([name]) =>
              ![
                'content-encoding',
                'content-length',
                'transfer-encoding',
              ].includes(name),
          ),
        ),
      );
      response.end(Buffer.from(await upstream.arrayBuffer()));
    }
  });
  await new Promise<void>((resolve) => server!.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

test.afterAll(async () => {
  release?.();
  if (server)
    await new Promise<void>((resolve) => server!.close(() => resolve()));
});

test('shared desktop page stays stable when streamed HTML starts overflowing', async ({
  page,
  browser,
}, testInfo) => {
  await page.addInitScript(() => {
    window.layoutShiftScore = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as PerformanceEntry & {
          value: number;
          hadRecentInput: boolean;
        };
        if (!shift.hadRecentInput) window.layoutShiftScore += shift.value;
      }
    }).observe({ type: 'layout-shift', buffered: true });
  });
  await page.goto(
    `${origin}/?currency=KRW&amount=1000000000&direction=twd-to-foreign`,
    { waitUntil: 'commit' },
  );
  try {
    await expect(page.locator('#route-code')).toHaveText('JPY');
    const geometry = async () => {
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
      );
      return page.evaluate(() => ({
        main: document.querySelector('main')!.getBoundingClientRect().toJSON(),
        gutter: innerWidth - document.body.clientWidth,
        cls: window.layoutShiftScore,
      }));
    };
    const before = await geometry();
    release!();
    await page.waitForLoadState('networkidle');
    const after = await geometry();
    await expect(page.locator('#comparison-context')).toHaveText('TWD → KRW');
    expect(after.main.x).toBe(before.main.x);
    expect(after.gutter).toBe(before.gutter);
    expect(after.cls).toBe(0);
    if (process.platform === 'linux') expect(before.gutter).toBe(15);
    await testInfo.attach('streaming-layout', {
      body: JSON.stringify({
        browser: browser.version(),
        platform: process.platform,
        before,
        after,
      }),
      contentType: 'application/json',
    });
  } finally {
    release?.();
  }
});
