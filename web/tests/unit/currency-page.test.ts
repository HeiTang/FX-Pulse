import assert from 'node:assert/strict';
import { test } from 'node:test';
import { currencyPage, jcbSourceUrl } from '../../src/lib/currency-page';
import { currencies, type RateDays } from '../../src/lib/rates';

test('all currency pages have matching paths, names and descriptions', () => {
  for (const [code, info] of Object.entries(currencies)) {
    const page = currencyPage(code);
    assert.equal(page.path, `/${code.toLowerCase()}/`);
    assert.equal(page.heading, `${info.name}刷卡匯率比較與試算`);
    assert.ok(page.title.startsWith(page.heading));
    assert.ok(page.description.includes(`${info.name}（${code}）`));
  }
});

test('JCB source uses the latest valid rate date for the selected currency', () => {
  const days: RateDays = {
    '2026-01-01': { JCB: { JPY: { rate: 1, reverse: 1 } } },
    '2026-01-02': { JCB: { USD: { rate: 2, reverse: 1 } } },
  };
  const dates = Object.keys(days);
  assert.equal(
    jcbSourceUrl(days, dates, 'JPY'),
    'https://www.jcb.jp/rate/usd01012026.html',
  );
  assert.equal(
    jcbSourceUrl(days, dates, 'USD'),
    'https://www.jcb.jp/rate/usd01022026.html',
  );
  assert.equal(jcbSourceUrl(days, dates, 'EUR'), 'https://www.jcb.jp/');
});
