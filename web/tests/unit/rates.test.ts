import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import {
  availableDates,
  fractionDigits,
  historyDates,
  rateEntries,
  sources,
  validateAmount,
  validDate,
  validRate,
  formatFetchedAt,
  type RateDays,
} from '../../src/lib/rates';

test('amount validation respects currency precision and grouping', () => {
  for (const code of ['JPY', 'KRW']) {
    assert.equal(fractionDigits(code), 0);
    assert.equal(validateAmount('10,000', code).value, 10000);
    assert.equal(validateAmount('1.0', code).value, null);
  }
  for (const code of ['USD', 'EUR', 'GBP', 'HKD', 'AUD', 'SGD']) {
    assert.equal(validateAmount('123.45', code).value, 123.45);
    assert.equal(validateAmount('123.456', code).value, null);
  }
  for (const raw of [
    '',
    ' ',
    '0',
    '-1',
    'NaN',
    'Infinity',
    '1e6',
    '1,00',
    '1000000001',
    '<script>',
  ]) {
    assert.equal(validateAmount(raw, 'USD').value, null, raw);
    assert.ok(validateAmount(raw, 'USD').error);
  }
  assert.equal(validateAmount('1,000,000,000', 'JPY').value, 1e9);
});

test('history uses calendar days including gaps and selected-date cutoff', () => {
  const dates = [
    '2026-01-01',
    '2026-01-04',
    '2026-01-05',
    '2026-01-10',
    '2026-01-11',
  ];
  assert.deepEqual(historyDates(dates, '2026-01-10', '7'), [
    '2026-01-04',
    '2026-01-05',
    '2026-01-10',
  ]);
  assert.deepEqual(
    historyDates(dates, '2026-01-10', 'all'),
    dates.slice(0, -1),
  );
  assert.deepEqual(historyDates(dates, 'invalid', '30'), []);
  assert.equal(validDate('2026-02-30'), false);
});

test('missing and invalid rates do not become comparison candidates or dates', () => {
  const days: RateDays = {
    '2026-01-01': { VISA: { USD: { rate: NaN, reverse: 1 } } },
    '2026-01-02': {
      Mastercard: { USD: { rate: 32, reverse: 1 / 32 } },
      JCB: { USD: { rate: -1, reverse: 1 } },
    },
    '2026-01-03': {},
    invalid: { VISA: { USD: { rate: 30, reverse: 1 / 30 } } },
  };
  assert.deepEqual(availableDates(days), ['2026-01-02']);
  assert.deepEqual(rateEntries(days, 'USD', '2026-01-02'), [
    { src: 'Mastercard', rate: 32 },
  ]);
  assert.deepEqual(rateEntries(days, 'JPY', '2026-01-02'), []);
  assert.deepEqual(availableDates({}), []);
  assert.equal(formatFetchedAt(''), '未提供');
  assert.equal(
    formatFetchedAt('2026-01-01T00:00:00Z'),
    '2026年1月1日 上午8:00',
  );
});

test('checked-in dataset has valid dates, supported currencies and finite positive rates', () => {
  const data = JSON.parse(
    readFileSync(new URL('../../src/data/rates.json', import.meta.url), 'utf8'),
  );
  assert.equal(data.meta.base, 'TWD');
  assert.equal(new Set(data.meta.currencies).size, data.meta.currencies.length);
  assert.ok(Number.isFinite(Date.parse(data.meta.last_updated)));
  assert.ok(availableDates(data.rates).length > 0);
  for (const [date, day] of Object.entries(data.rates) as [
    string,
    RateDays[string],
  ][]) {
    assert.ok(validDate(date), date);
    for (const [source, rates] of Object.entries(day)) {
      assert.ok(sources.includes(source as (typeof sources)[number]), source);
      assert.ok(Object.keys(rates!).length > 0);
      for (const [code, entry] of Object.entries(rates!)) {
        assert.ok(data.meta.currencies.includes(code), code);
        assert.ok(validRate(entry.rate), `${date}/${source}/${code}/rate`);
        assert.ok(
          validRate(entry.reverse),
          `${date}/${source}/${code}/reverse`,
        );
      }
    }
  }
});
