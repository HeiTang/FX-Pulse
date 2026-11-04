import { currencies, rateEntries, type RateDays } from './rates';

export function currencyPage(code: string) {
  const heading = `${currencies[code].name}刷卡匯率比較與試算`;
  return {
    path: `/${code.toLowerCase()}/`,
    heading,
    title: `${heading}｜VISA、Mastercard、JCB — FX Pulse`,
    description: `比較 ${currencies[code].name}（${code}）兌台幣的 VISA、Mastercard 與 JCB 參考匯率，查看歷史資料並試算刷卡金額。JCB 為交叉匯率估算，未計銀行手續費與回饋。`,
  };
}

export function jcbSourceUrl(days: RateDays, dates: string[], code: string) {
  const date = dates.findLast((date) =>
    rateEntries(days, code, date).some((entry) => entry.src === 'JCB'),
  );
  return date
    ? `https://www.jcb.jp/rate/usd${date.slice(5, 7)}${date.slice(8, 10)}${date.slice(0, 4)}.html`
    : 'https://www.jcb.jp/';
}
