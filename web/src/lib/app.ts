import ratesData from '../data/rates.json';
import { mountDatePicker } from './date-picker';
import {
  sources,
  currencies,
  colors,
  availableDates,
  fractionDigits,
  historyDates,
  periodComparison,
  rateEntries,
  validRate,
  validDate,
  conversionRate,
  validateAmount,
  type Source,
  type RateDays,
} from './rates';
const rateDays: RateDays = ratesData.rates;
const dates = availableDates(rateDays);
const currency = document.querySelector<HTMLInputElement>('#currency')!;
const amount = document.querySelector<HTMLInputElement>('#amount')!;
const rateDate = document.querySelector<HTMLInputElement>('#rate-date')!;
const results = document.querySelector<HTMLElement>('#results')!;
const chartEl = document.querySelector<HTMLElement>('#chart')!;
const params = new URLSearchParams(location.search);
const requestedCurrency = params.get('currency');
const supportedCurrency =
  requestedCurrency !== null &&
  ratesData.meta.currencies.includes(requestedCurrency);
if (supportedCurrency) currency.value = requestedCurrency!;
if (params.has('amount')) amount.value = params.get('amount')!;
const requestedDate = params.get('date');
if (requestedDate !== null) {
  if (validDate(requestedDate)) {
    rateDate.value = requestedDate;
    if (!dates.includes(requestedDate))
      document.querySelector<HTMLElement>('#date-error')!.textContent =
        '此日期無資料';
  } else {
    document.querySelector<HTMLElement>('#date-error')!.textContent =
      '連結日期無效，請使用 YYYY-MM-DD。';
  }
}
let selectedDate = rateDate.value;
mountDatePicker(rateDate, dates);
let reverse = params.get('direction') === 'twd-to-foreign';
const queryErrors: string[] = [];
if (params.has('currency') && !supportedCurrency)
  queryErrors.push('連結幣別不支援，已使用預設幣別。');
if (
  params.has('direction') &&
  !['foreign-to-twd', 'twd-to-foreign'].includes(params.get('direction')!)
)
  queryErrors.push('連結換算方向無效，已使用預設方向。');
document.querySelector<HTMLElement>('#query-message')!.textContent =
  queryErrors.join(' ');
const swap = document.querySelector<HTMLButtonElement>('#swap-direction')!;
const board = document.querySelector<HTMLElement>('.route-board')!;
const foreignRoute = document.querySelector<HTMLElement>('.currency-field')!;
const twdRoute = document.querySelector<HTMLElement>('.route-destination')!;
function syncDirection() {
  board.replaceChildren(
    reverse ? twdRoute : foreignRoute,
    swap,
    reverse ? foreignRoute : twdRoute,
  );
  board.classList.toggle('is-reversed', reverse);
  swap.setAttribute('aria-pressed', String(reverse));
}
syncDirection();
const inputCode = () => (reverse ? 'TWD' : currency.value);
let range: '7' | '30' | 'all' = '7';
let source: Source | 'all' = 'all';
let chart: ReturnType<typeof import('./chart').createChart> | null = null;
let chartModule: Promise<typeof import('./chart')> | null = null;
let chartVersion = 0;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

const formatMoney = (value: number, code: string) =>
  new Intl.NumberFormat('zh-TW', {
    minimumFractionDigits: fractionDigits(code),
    maximumFractionDigits: fractionDigits(code),
  }).format(value);
const unit = (code: string) => (code === 'TWD' ? 'NT$' : code);
const shortcutRateFormat = new Intl.NumberFormat('zh-TW', {
  maximumSignificantDigits: 4,
});
const rateFormat = (n: number) => (n < 1 ? n.toFixed(6) : n.toFixed(4));
const setText = (selector: string, value: string) => {
  document.querySelector<HTMLElement>(selector)!.textContent = value;
};
const amountError = () => validateAmount(amount.value, inputCode()).error;
const validAmount = () => validateAmount(amount.value, inputCode()).value;
const entries = (code: string, day: string) =>
  rateEntries(rateDays, code, day, reverse);
function syncQuery() {
  const url = new URL(location.href);
  url.searchParams.set('currency', currency.value);
  url.searchParams.set('amount', amount.value);
  url.searchParams.set('date', rateDate.value);
  url.searchParams.set(
    'direction',
    reverse ? 'twd-to-foreign' : 'foreign-to-twd',
  );
  if (url.href !== location.href) history.replaceState(history.state, '', url);
}
function renderResults() {
  syncQuery();
  const code = currency.value;
  const value = validAmount();
  const available = entries(code, rateDate.value);
  const from = inputCode();
  const to = reverse ? code : 'TWD';
  const bestValue = available.length
    ? (reverse ? Math.max : Math.min)(
        ...available.map((item) => item.rate * (value ?? 1)),
      )
    : null;
  setText('#comparison-context', `${from} → ${to}`);
  setText('#amount-code', from);
  setText('#amount-label', reverse ? '台幣預算' : '消費金額');
  setText('#foreign-label', reverse ? '換算幣別' : '消費幣別');
  setText('#twd-label', reverse ? '預算幣別' : '換算幣別');
  setText('#rate-heading', `每 1 ${from} 匯率`);
  setText('#total-heading', `換算${reverse ? currencies[code].name : '台幣'}`);
  setText('#difference-heading', reverse ? '與最高值的差額' : '與最低值的差額');
  setText(
    '#conversion-note-text',
    reverse
      ? '依刷卡參考匯率反推可換得金額，非銀行實際換匯報價；未計手續費與回饋。JCB 為交叉匯率估算。'
      : '未計銀行手續費與回饋，非實際帳單。JCB 為交叉匯率估算。',
  );
  setText('#route-code', code);
  setText('#route-name', currencies[code]?.name ?? code);
  setText('#route-flag', currencies[code]?.flag ?? '');
  const error = document.querySelector<HTMLElement>('#amount-error')!;
  error.textContent = amountError();
  amount.inputMode = fractionDigits(from) === 0 ? 'numeric' : 'decimal';
  amount.setAttribute('aria-invalid', String(value === null));
  results.replaceChildren();
  for (const src of sources) {
    const rate = available.find((item) => item.src === src)?.rate;
    const converted =
      value !== null && rate !== undefined ? value * rate : null;
    const best =
      converted !== null &&
      bestValue !== null &&
      Math.abs(converted - bestValue) < 0.0000001 &&
      available.length > 1;
    const row = document.createElement('div');
    row.className = `result-row${best ? ' is-best' : ''}`;
    const label = document.createElement('div');
    label.className = 'result-source';
    const icon = document.createElement('span');
    icon.className = 'source-icon';
    icon.setAttribute('aria-hidden', 'true');
    const logo = document.createElement('img');
    logo.src = `/icons/${src.toLowerCase()}.svg`;
    logo.alt = '';
    icon.append(logo);
    const name = document.createElement('strong');
    name.textContent = src;
    label.append(icon, name);
    if (src === 'JCB') {
      const estimate = document.createElement('span');
      estimate.className = 'source-estimate';
      estimate.textContent = '交叉匯率估算';
      label.append(estimate);
    }
    const rateCell = document.createElement('div');
    rateCell.className = 'result-rate';
    const rateNumber = document.createElement('span');
    rateNumber.textContent =
      rate === undefined
        ? src === 'JCB' &&
          [0, 6].includes(new Date(`${rateDate.value}T00:00:00Z`).getUTCDay())
          ? '此日期無資料；目前抓取策略略過週末'
          : '此日期無資料'
        : `1 ${from} = ${rateFormat(rate)} ${to}`;
    rateCell.append(rateNumber);
    const total = document.createElement('div');
    total.className = 'result-total';
    const totalNumber = document.createElement('strong');
    totalNumber.textContent =
      converted === null
        ? '—'
        : `${src === 'JCB' ? '約 ' : ''}${unit(to)} ${formatMoney(converted, to)}`;
    total.append(totalNumber);
    const difference = document.createElement('div');
    difference.className = 'result-difference';
    const gap =
      converted !== null && bestValue !== null
        ? Math.abs(converted - bestValue)
        : null;
    const smallestUnit = 10 ** -fractionDigits(to);
    const sign = reverse ? '−' : '+';
    difference.textContent =
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
    if (best) difference.classList.add('best-badge');
    const headline = document.createElement('div');
    headline.className = 'result-headline';
    headline.append(label, total);
    const details = document.createElement('div');
    details.className = 'result-details';
    details.append(rateCell, difference);
    row.append(headline, details);
    results.append(row);
  }
  setText(
    '#comparison-message',
    available.length === 0
      ? '此幣別在所選日期沒有可用匯率。'
      : available.length < 2
        ? '此日期可用來源不足，無法計算差額。'
        : '',
  );
}
function renderCurrencyShortcuts() {
  setText(
    '#shortcut-hint-text',
    reverse
      ? '每 1 TWD 可換得的最高參考外幣金額 · 所選日期'
      : '每 1 外幣 → TWD · 最低參考匯率 · 所選日期',
  );
  for (const button of document.querySelectorAll<HTMLButtonElement>(
    '[data-quick-currency]',
  )) {
    const code = button.dataset.quickCurrency!;
    const available = entries(code, rateDate.value).sort((a, b) =>
      reverse ? b.rate - a.rate : a.rate - b.rate,
    );
    button.setAttribute('aria-pressed', String(code === currency.value));
    const best = available[0];
    const rateText = best
      ? `${best.src === 'JCB' ? '約 ' : ''}${shortcutRateFormat.format(best.rate)}`
      : '—';
    button.querySelector<HTMLElement>('[data-shortcut-rate]')!.textContent =
      rateText;
    button.setAttribute(
      'aria-label',
      `${currencies[code]?.name ?? code} ${code}，每 1 ${reverse ? 'TWD' : code} 可換得 ${reverse ? code : 'TWD'} ${rateText}，${best ? `${best.src}${best.src === 'JCB' ? '（估算）' : ''}` : '此日期無資料'}`,
    );
  }
}
function renderPeriodComparison(
  visibleDates = historyDates(dates, rateDate.value, range),
) {
  const code = currency.value;
  const value = validAmount();
  const comparison = periodComparison(
    rateDays,
    visibleDates,
    code,
    value,
    reverse,
  );
  const from = inputCode();
  const to = reverse ? code : 'TWD';
  const qualifier = reverse ? '可換最多' : '最低';
  setText(
    '#period-context',
    `${range === 'all' ? '全部期間' : `近 ${range} 天`} · ${code} · 三家比較`,
  );
  setText('#period-dates', `截至 ${rateDate.value}`);
  setText('#period-count', `${comparison.count} 天`);
  for (const src of sources) {
    setText(
      `#period-${src.toLowerCase()}-label`,
      `${src} ${qualifier}${src === 'JCB' ? '（估算）' : ''}`,
    );
    setText(`#period-${src.toLowerCase()}`, `${comparison.bestDays[src]} 天`);
  }
  setText('#period-tied-label', reverse ? '最多並列' : '最低並列');
  setText('#period-tied', `${comparison.tied} 天`);
  setText(
    '#period-amount',
    value === null
      ? '請輸入有效金額以比較差額'
      : `換算 ${formatMoney(value, from)} ${from} → ${to}`,
  );
  const differenceText = (difference: number | null) =>
    difference === null ? '—' : `約 ${unit(to)} ${formatMoney(difference, to)}`;
  setText('#period-median', differenceText(comparison.median));
  setText('#period-maximum', differenceText(comparison.maximum));
  setText(
    '#period-message',
    comparison.count === 0
      ? '所選期間沒有同日、同幣別且三家都有有效匯率的資料。'
      : '',
  );
}
async function renderChart() {
  const version = ++chartVersion;
  const code = currency.value;
  const reversed = reverse;
  const from = reversed ? 'TWD' : code;
  const to = reversed ? code : 'TWD';
  setText('#chart-title', `${from} / ${to}`);
  setText(
    '#chart-note',
    `1 ${from} = ${to} · 截至所選日期 · 線段可能跨過缺資料日`,
  );
  const visibleDates = historyDates(dates, rateDate.value, range);
  renderPeriodComparison(visibleDates);
  const visibleSources = source === 'all' ? sources : [source];
  const hasEnough = visibleSources.some(
    (src) =>
      visibleDates.filter((date) =>
        validRate(conversionRate(rateDays[date]?.[src]?.[code], reversed)),
      ).length >= 2,
  );
  const placeholder =
    document.querySelector<HTMLElement>('#chart-placeholder')!;
  placeholder.textContent = '所選範圍的資料不足，至少需要兩個日期的匯率。';
  chartEl.hidden = !hasEnough;
  placeholder.hidden = hasEnough;
  chartEl.setAttribute(
    'aria-label',
    `${from} 對 ${to}，${visibleDates[0] ?? ''} 至 ${visibleDates.at(-1) ?? ''}，${visibleSources.join('、')} 匯率走勢`,
  );
  if (!hasEnough) {
    chart?.clear();
    return;
  }
  try {
    chartModule ??= import('./chart');
    const { createChart } = await chartModule;
    if (version !== chartVersion) return;
    chart ??= createChart(chartEl);
  } catch {
    if (version !== chartVersion) return;
    chartModule = null;
    chartEl.hidden = true;
    placeholder.hidden = false;
    placeholder.textContent = '圖表載入失敗，請重新整理頁面。';
    return;
  }
  chart.setOption(
    {
      animation: !reducedMotion.matches,
      animationDuration: 250,
      grid: { left: 62, right: 18, top: 20, bottom: 42 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#263244',
        borderWidth: 0,
        textStyle: { color: '#fff', fontSize: 12 },
        valueFormatter: (value: unknown) =>
          value == null ? '無資料' : `${unit(to)} ${rateFormat(Number(value))}`,
      },
      xAxis: {
        type: 'category',
        data: visibleDates,
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#354259' } },
        axisTick: { show: false },
        axisLabel: {
          color: '#a1aec1',
          hideOverlap: true,
          formatter: (date: string) => date.slice(5),
        },
      },
      yAxis: {
        type: 'value',
        scale: true,
        splitNumber: 4,
        axisLine: { show: false },
        axisLabel: {
          color: '#a1aec1',
          formatter: (value: number) => rateFormat(value),
        },
        splitLine: { lineStyle: { color: '#293346' } },
      },
      series: visibleSources.map((src) => ({
        name: src,
        type: 'line',
        data: visibleDates.map((date) => {
          const rate = conversionRate(rateDays[date]?.[src]?.[code], reversed);
          return validRate(rate) ? rate : null;
        }),
        connectNulls: true,
        showSymbol: visibleDates.length <= 7,
        symbol: 'circle',
        symbolSize: 5,
        smooth: false,
        lineStyle: { color: colors[src], width: 2 },
        itemStyle: { color: colors[src] },
        emphasis: { focus: 'series' },
      })),
    },
    true,
  );
  chart.resize();
}
function render() {
  renderResults();
  renderCurrencyShortcuts();
  renderChart();
}
document
  .querySelectorAll<HTMLButtonElement>('[data-quick-currency]')
  .forEach((button) =>
    button.addEventListener('click', () => {
      currency.value = button.dataset.quickCurrency!;
      render();
    }),
  );
let swapAnimations: Animation[] = [];
function cancelSwapAnimations() {
  swapAnimations.forEach((animation) => animation.cancel());
  swapAnimations = [];
}
reducedMotion.addEventListener('change', () => {
  if (reducedMotion.matches) cancelSwapAnimations();
});
swap.addEventListener('click', () => {
  cancelSwapAnimations();
  reverse = !reverse;
  syncDirection();
  render();
  swap.focus({ preventScroll: true });
  if (reducedMotion.matches) return;
  const timing = { duration: 240, easing: 'cubic-bezier(0.2, 0.7, 0.3, 1)' };
  const left = reverse ? twdRoute : foreignRoute;
  const right = reverse ? foreignRoute : twdRoute;
  swapAnimations = [
    left.animate(
      [
        { transform: 'translateX(18px)', opacity: 0.35 },
        { transform: 'translateX(0)', opacity: 1 },
      ],
      timing,
    ),
    right.animate(
      [
        { transform: 'translateX(-18px)', opacity: 0.35 },
        { transform: 'translateX(0)', opacity: 1 },
      ],
      timing,
    ),
    swap
      .querySelector('span')!
      .animate(
        [
          { transform: `rotate(${reverse ? -180 : 180}deg)` },
          { transform: 'rotate(0deg)' },
        ],
        timing,
      ),
    results.animate(
      [
        { transform: 'translateY(4px)', opacity: 0.55 },
        { transform: 'translateY(0)', opacity: 1 },
      ],
      { ...timing, duration: 180 },
    ),
  ];
});
amount.addEventListener('input', () => {
  renderResults();
  renderPeriodComparison();
});
amount.addEventListener('focus', () => {
  if (validAmount() !== null) amount.value = amount.value.replaceAll(',', '');
  amount.select();
});
amount.addEventListener('blur', () => {
  const value = validAmount();
  if (value !== null)
    amount.value = new Intl.NumberFormat('en-US', {
      maximumFractionDigits: fractionDigits(inputCode()),
    }).format(value);
  renderResults();
  renderPeriodComparison();
});
amount.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') amount.blur();
});
rateDate.addEventListener('change', () => {
  if (!rateDate.validity.valid || !dates.includes(rateDate.value)) {
    rateDate.value = selectedDate;
    setText('#date-error', `可選日期：${dates[0]} 至 ${dates.at(-1)}`);
    return;
  }
  selectedDate = rateDate.value;
  setText('#date-error', '');
  render();
});
document.querySelectorAll<HTMLButtonElement>('[data-range]').forEach((button) =>
  button.addEventListener('click', () => {
    range = button.dataset.range as typeof range;
    document
      .querySelectorAll<HTMLButtonElement>('[data-range]')
      .forEach((item) =>
        item.setAttribute('aria-pressed', String(item === button)),
      );
    renderChart();
  }),
);
document
  .querySelectorAll<HTMLButtonElement>('[data-source]')
  .forEach((button) =>
    button.addEventListener('click', () => {
      source = button.dataset.source as typeof source;
      document
        .querySelectorAll<HTMLButtonElement>('[data-source]')
        .forEach((item) =>
          item.setAttribute('aria-pressed', String(item === button)),
        );
      renderChart();
    }),
  );
const chartObserver = new ResizeObserver(() => chart?.resize());
chartObserver.observe(chartEl);
render();
