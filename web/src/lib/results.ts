import { fractionDigits, rateEntries, sources, type RateDays } from './rates';

export const formatMoney = (value: number, code: string) =>
  new Intl.NumberFormat('zh-TW', {
    minimumFractionDigits: fractionDigits(code),
    maximumFractionDigits: fractionDigits(code),
  }).format(value);
export const unit = (code: string) => (code === 'TWD' ? 'NT$' : code);
export const rateFormat = (n: number) => (n < 1 ? n.toFixed(6) : n.toFixed(4));

export function resultRows(
  days: RateDays,
  code: string,
  date: string,
  value: number | null,
  reverse = false,
) {
  const available = rateEntries(days, code, date, reverse);
  const from = reverse ? 'TWD' : code;
  const to = reverse ? code : 'TWD';
  const bestValue = available.length
    ? (reverse ? Math.max : Math.min)(
        ...available.map((item) => item.rate * (value ?? 1)),
      )
    : null;
  return sources.map((src) => {
    const rate = available.find((item) => item.src === src)?.rate;
    const converted =
      value !== null && rate !== undefined ? value * rate : null;
    const best =
      converted !== null &&
      bestValue !== null &&
      Math.abs(converted - bestValue) < 0.0000001 &&
      available.length > 1;
    const rateText =
      rate === undefined
        ? src === 'JCB' &&
          [0, 6].includes(new Date(`${date}T00:00:00Z`).getUTCDay())
          ? '此日期無資料；目前抓取策略略過週末'
          : '此日期無資料'
        : `1 ${from} = ${rateFormat(rate)} ${to}`;
    const totalText =
      converted === null
        ? '—'
        : `${src === 'JCB' ? '約 ' : ''}${unit(to)} ${formatMoney(converted, to)}`;
    const gap =
      converted !== null && bestValue !== null
        ? Math.abs(converted - bestValue)
        : null;
    const smallestUnit = 10 ** -fractionDigits(to);
    const sign = reverse ? '−' : '+';
    const differenceText =
      converted === null
        ? '—'
        : best
          ? reverse
            ? src === 'JCB'
              ? '最高參考可換得金額（估算）'
              : '最高可換得金額'
            : src === 'JCB'
              ? '最低參考換算額（估算）'
              : '最低換算額'
          : gap === null || available.length < 2
            ? '無法比較'
            : gap < smallestUnit / 2
              ? `${sign} 小於 ${unit(to)} ${formatMoney(smallestUnit, to)}`
              : `${sign} ${unit(to)} ${formatMoney(gap, to)}`;
    return { src, best, rateText, totalText, differenceText };
  });
}
