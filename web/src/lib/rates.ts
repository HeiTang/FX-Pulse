export const sources = ['VISA', 'Mastercard', 'JCB'] as const;
export type Source = (typeof sources)[number];
export type Rate = { rate: number; reverse: number };
export type Day = Partial<Record<Source, Record<string, Rate>>>;
export type RateDays = Record<string, Day>;
export const currencies: Record<string, { name: string; flag: string }> = {
  JPY: { name: '日圓', flag: '🇯🇵' },
  USD: { name: '美元', flag: '🇺🇸' },
  EUR: { name: '歐元', flag: '🇪🇺' },
  GBP: { name: '英鎊', flag: '🇬🇧' },
  HKD: { name: '港幣', flag: '🇭🇰' },
  AUD: { name: '澳幣', flag: '🇦🇺' },
  KRW: { name: '韓元', flag: '🇰🇷' },
  SGD: { name: '新加坡幣', flag: '🇸🇬' },
};
export const colors: Record<Source, string> = {
  VISA: '#6c9fff',
  Mastercard: '#b7a0f4',
  JCB: '#c2eb74',
};

export function validRate(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

export function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return (
    Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
  );
}

export function availableDates(days: RateDays): string[] {
  return Object.keys(days)
    .filter(
      (date) =>
        validDate(date) &&
        sources.some((source) =>
          Object.values(days[date][source] ?? {}).some((entry) =>
            validRate(entry.rate),
          ),
        ),
    )
    .sort();
}

export function conversionRate(
  entry: Rate | undefined,
  reverse = false,
): number | undefined {
  if (!validRate(entry?.rate)) return undefined;
  const value = reverse ? 1 / entry.rate : entry.rate;
  return validRate(value) ? value : undefined;
}

export function rateEntries(
  days: RateDays,
  code: string,
  date: string,
  reverse = false,
) {
  return sources
    .map((src) => ({
      src,
      rate: conversionRate(days[date]?.[src]?.[code], reverse),
    }))
    .filter((entry): entry is { src: Source; rate: number } =>
      validRate(entry.rate),
    );
}

export function historyDates(
  dates: string[],
  cutoff: string,
  range: '7' | '30' | 'all',
): string[] {
  if (!validDate(cutoff)) return [];
  if (range === 'all') return dates.filter((date) => date <= cutoff);
  const start = new Date(`${cutoff}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - Number(range) + 1);
  const from = start.toISOString().slice(0, 10);
  return dates.filter((date) => date >= from && date <= cutoff);
}

export function formatFetchedAt(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '未提供';
  return new Intl.DateTimeFormat('zh-TW', {
    timeZone: 'Asia/Taipei',
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

const digits = new Map<string, number>();
export function fractionDigits(code: string): number {
  if (!digits.has(code))
    digits.set(
      code,
      new Intl.NumberFormat('en', {
        style: 'currency',
        currency: code,
      }).resolvedOptions().maximumFractionDigits ?? 2,
    );
  return digits.get(code)!;
}

export function validateAmount(
  raw: string,
  code: string,
): { value: number | null; error: string } {
  raw = raw.trim();
  let error = '';
  if (!raw) error = '請輸入金額。';
  else if (!/^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d*)?$/.test(raw))
    error = '請輸入有效的數字金額。';
  else {
    const precision = fractionDigits(code);
    const fractional = raw.split('.')[1];
    const value = Number(raw.replaceAll(',', ''));
    if (
      fractional !== undefined &&
      (precision === 0 || fractional.length > precision)
    )
      error =
        precision === 0
          ? `${code} 金額需為整數。`
          : `${code} 最多可輸入 ${precision} 位小數。`;
    else if (!Number.isFinite(value) || value > 1_000_000_000)
      error = '金額上限為 10 億。';
    else if (value <= 0) error = '請輸入大於 0 的金額。';
  }
  return { value: error ? null : Number(raw.replaceAll(',', '')), error };
}
