import ratesData from '../data/rates.json';
import { mountDatePicker } from './date-picker';
import {
  sources,
  currencies,
  colors,
  availableDates,
  fractionDigits,
  historyDates,
  rateEntries,
  validRate,
  validateAmount,
  type Source,
  type RateDays,
} from './rates';
const rateDays: RateDays = ratesData.rates;
const dates = availableDates(rateDays);
const currency = document.querySelector<HTMLSelectElement>('#currency')!;
const amount = document.querySelector<HTMLInputElement>('#amount')!;
const rateDate = document.querySelector<HTMLInputElement>('#rate-date')!;
let selectedDate = rateDate.value;
mountDatePicker(rateDate, dates);
const results = document.querySelector<HTMLElement>('#results')!;
const chartEl = document.querySelector<HTMLElement>('#chart')!;
const params = new URLSearchParams(location.search);
if (
  Array.from(currency.options).some(
    (option) => option.value === params.get('currency'),
  )
)
  currency.value = params.get('currency')!;
if (params.has('amount')) amount.value = params.get('amount')!;
let range: '7' | '30' | 'all' = '7';
let source: Source | 'all' = 'all';
let chart: ReturnType<typeof import('./chart').createChart> | null = null;
let chartModule: Promise<typeof import('./chart')> | null = null;
let chartVersion = 0;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

const money = new Intl.NumberFormat('zh-TW', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const decimal = new Intl.NumberFormat('zh-TW', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const rateFormat = (n: number) => (n < 1 ? n.toFixed(6) : n.toFixed(4));
const setText = (selector: string, value: string) => {
  document.querySelector<HTMLElement>(selector)!.textContent = value;
};
const amountError = () => validateAmount(amount.value, currency.value).error;
const validAmount = () => validateAmount(amount.value, currency.value).value;
const entries = (code: string, day: string) => rateEntries(rateDays, code, day);
function renderResults() {
  const code = currency.value;
  const value = validAmount();
  const available = entries(code, rateDate.value);
  const min = available.length
    ? Math.min(...available.map((item) => item.rate * (value ?? 1)))
    : null;
  setText('#comparison-context', `${code} → TWD`);
  setText('#amount-code', code);
  setText('#route-code', code);
  setText('#route-flag', currencies[code]?.flag ?? '');
  const error = document.querySelector<HTMLElement>('#amount-error')!;
  error.textContent = amountError();
  amount.inputMode = fractionDigits(code) === 0 ? 'numeric' : 'decimal';
  amount.setAttribute('aria-invalid', String(value === null));
  results.replaceChildren();
  for (const src of sources) {
    const rate = available.find((item) => item.src === src)?.rate;
    const converted =
      value !== null && rate !== undefined ? value * rate : null;
    const best =
      converted !== null &&
      min !== null &&
      Math.abs(converted - min) < 0.0000001 &&
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
    const rateCell = document.createElement('div');
    rateCell.className = 'result-rate';
    const rateNumber = document.createElement('span');
    rateNumber.textContent =
      rate === undefined
        ? '此日期無資料'
        : `1 ${code} = ${rateFormat(rate)} TWD`;
    rateCell.append(rateNumber);
    const total = document.createElement('div');
    total.className = 'result-total';
    const totalNumber = document.createElement('strong');
    totalNumber.textContent =
      converted === null ? '—' : `NT$ ${money.format(converted)}`;
    total.append(totalNumber);
    const difference = document.createElement('div');
    difference.className = 'result-difference';
    difference.textContent =
      converted === null
        ? '—'
        : best
          ? '最低換算額'
          : min === null || available.length < 2
            ? '無法比較'
            : converted - min < 0.005
              ? '+ 小於 NT$ 0.01'
              : `+ NT$ ${decimal.format(converted - min)}`;
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
function renderOverview() {
  for (const button of document.querySelectorAll<HTMLButtonElement>(
    '.currency-card',
  )) {
    const code = button.dataset.currency!;
    const available = entries(code, rateDate.value).sort(
      (a, b) => a.rate - b.rate,
    );
    button.classList.toggle('active', code === currency.value);
    button.setAttribute('aria-pressed', String(code === currency.value));
    button.querySelector<HTMLElement>('[data-card-rate]')!.textContent =
      available.length ? `NT$ ${rateFormat(available[0].rate)}` : '—';
    button.querySelector<HTMLElement>('[data-card-source]')!.textContent =
      available.length ? `${available[0].src} · 1 ${code}` : '此日期無資料';
  }
}
async function renderChart() {
  const version = ++chartVersion;
  const code = currency.value;
  setText('#chart-title', `${code} / TWD`);
  const visibleDates = historyDates(dates, rateDate.value, range);
  const visibleSources = source === 'all' ? sources : [source];
  const hasEnough = visibleSources.some(
    (src) =>
      visibleDates.filter((date) =>
        validRate(rateDays[date]?.[src]?.[code]?.rate),
      ).length >= 2,
  );
  const placeholder =
    document.querySelector<HTMLElement>('#chart-placeholder')!;
  placeholder.textContent = '所選範圍的資料不足，至少需要兩個日期的匯率。';
  chartEl.hidden = !hasEnough;
  placeholder.hidden = hasEnough;
  chartEl.setAttribute(
    'aria-label',
    `${code} 對台幣，${visibleDates[0] ?? ''} 至 ${visibleDates.at(-1) ?? ''}，${visibleSources.join('、')} 匯率走勢`,
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
          value == null ? '無資料' : `NT$ ${rateFormat(Number(value))}`,
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
          const rate = rateDays[date]?.[src]?.[code]?.rate;
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
  renderOverview();
  renderChart();
  document
    .querySelectorAll<HTMLButtonElement>('[data-quick-currency]')
    .forEach((button) =>
      button.setAttribute(
        'aria-pressed',
        String(button.dataset.quickCurrency === currency.value),
      ),
    );
}
document
  .querySelectorAll<HTMLButtonElement>('[data-quick-currency]')
  .forEach((button) =>
    button.addEventListener('click', () => {
      currency.value = button.dataset.quickCurrency!;
      render();
    }),
  );
currency.addEventListener('change', render);
amount.addEventListener('input', renderResults);
amount.addEventListener('focus', () => amount.select());
amount.addEventListener('blur', () => {
  const value = validAmount();
  if (value !== null)
    amount.value = new Intl.NumberFormat('en-US', {
      maximumFractionDigits: fractionDigits(currency.value),
    }).format(value);
  renderResults();
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
document
  .querySelectorAll<HTMLButtonElement>('.currency-card')
  .forEach((button) =>
    button.addEventListener('click', () => {
      currency.value = button.dataset.currency!;
      render();
      document.querySelector('.workspace')?.scrollIntoView({
        behavior: reducedMotion.matches ? 'auto' : 'smooth',
        block: 'start',
      });
    }),
  );
const chartObserver = new ResizeObserver(() => chart?.resize());
chartObserver.observe(chartEl);
render();
