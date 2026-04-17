"""Validate JCB cross-rate (via jcb.jp) against Taiwan JCB PDF rates.

Formula: TWD/XXX = (TWD/USD sell) / (XXX/USD buy)

Usage:
    poetry run python scripts/validate_jcb_crossrate.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

from curl_cffi import requests as cf_requests

# ── Config ────────────────────────────────────────────────────────────────────

RATES_JSON = Path(__file__).parent.parent.parent / "web" / "src" / "data" / "rates.json"

# Currencies to verify (must exist in both PDF and jcb.jp)
VERIFY_CURRENCIES = ["JPY", "EUR", "KRW", "HKD"]

# Missing currencies we want to extend to
TARGET_CURRENCIES = ["GBP", "AUD", "SGD"]


# ── jcb.jp HTML Parser ────────────────────────────────────────────────────────


class RateTableParser(HTMLParser):
    """Parse the exchange rate table from jcb.jp/rate/usdMMDDYYYY.html.

    Actual table row structure:
      <td>USD</td><td>=</td><td>buy</td><td>mid</td><td>sell</td><td>CURRENCY</td>
    """

    def __init__(self) -> None:
        super().__init__()
        self._in_td = False
        self._current_row: list[str] = []
        self._rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag == "td":
            self._in_td = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self._in_td = False
        elif tag == "tr":
            if self._current_row:
                self._rows.append(self._current_row[:])
            self._current_row = []

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._current_row.append(data.strip())

    def get_rates(self) -> dict[str, dict[str, float]]:
        """Return {currency: {buy: float, mid: float, sell: float}}.

        Row format: [USD, =, buy, mid, sell, CURRENCY_CODE]
        """
        result: dict[str, dict[str, float]] = {}
        for row in self._rows:
            # Expect: ['USD', '=', '1.234', '1.235', '1.236', 'AUD']
            if len(row) < 6:
                continue
            if row[0] != "USD" or row[1] != "=":
                continue
            code = row[5].strip().upper()
            if len(code) != 3 or not code.isalpha():
                continue
            try:
                buy = float(row[2])
                mid = float(row[3])
                sell = float(row[4])
            except ValueError:
                continue
            result[code] = {"buy": buy, "mid": mid, "sell": sell}
        return result


# ── Fetch ─────────────────────────────────────────────────────────────────────


def fetch_jcbJP_rates(d: date) -> dict[str, dict[str, float]]:
    """Fetch raw XYZ/USD rates from jcb.jp for a given date."""
    url = f"https://www.jcb.jp/rate/usd{d.strftime('%m%d%Y')}.html"
    session = cf_requests.Session(impersonate="chrome120")
    resp = session.get(url, timeout=30)
    resp.raise_for_status()

    parser = RateTableParser()
    parser.feed(resp.text)
    rates = parser.get_rates()

    if not rates:
        raise ValueError(f"No rates parsed from {url}")

    print(f"  [{d}] Fetched {len(rates)} currencies from jcb.jp")
    return rates


def compute_cross_rate(
    raw: dict[str, dict[str, float]],
    target: str,
) -> float | None:
    """Compute TWD/target using cross-rate through USD.

    TWD/target = (TWD/USD sell) / (target/USD buy)
    """
    if "TWD" not in raw or target not in raw:
        return None
    twd_sell = raw["TWD"]["sell"]
    target_buy = raw[target]["buy"]
    if target_buy == 0:
        return None
    return twd_sell / target_buy


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    with open(RATES_JSON) as f:
        store = json.load(f)
    pdf_data = store["rates"]

    # Find dates that have JCB PDF data
    dates_with_jcb = sorted(
        [d for d in pdf_data if "JCB" in pdf_data[d]],
        reverse=True,
    )[:7]  # last 7 days

    if not dates_with_jcb:
        print("No JCB PDF data found.")
        sys.exit(1)

    print(f"\nValidating {len(VERIFY_CURRENCIES)} currencies over {len(dates_with_jcb)} days")
    print(f"Verify: {VERIFY_CURRENCIES}")
    print(f"Target (new): {TARGET_CURRENCIES}")
    print("=" * 70)

    # Collect results
    all_diffs: list[float] = []
    cross_rates_new: dict[str, dict[str, float]] = {c: {} for c in TARGET_CURRENCIES}

    for date_str in dates_with_jcb:
        d = date.fromisoformat(date_str)
        pdf_day = pdf_data[date_str]["JCB"]

        print(f"\n{date_str}")
        print(f"  {'Currency':<8} {'PDF rate':>12} {'Cross-rate':>12} {'Diff %':>8}")
        print(f"  {'-'*8} {'-'*12} {'-'*12} {'-'*8}")

        try:
            raw = fetch_jcbJP_rates(d)
        except Exception as e:
            print(f"  ERROR fetching jcb.jp: {e}")
            continue

        # Show raw TWD/USD rates for reference
        if "TWD" in raw:
            r = raw["TWD"]
            print(f"  TWD/USD buy={r['buy']:.6f} mid={r['mid']:.6f} sell={r['sell']:.6f}")

        # Verify known currencies
        for curr in VERIFY_CURRENCIES:
            pdf_rate = pdf_day.get(curr, {}).get("rate")
            cross = compute_cross_rate(raw, curr)

            if pdf_rate is None:
                print(f"  {curr:<8} {'N/A (no PDF)':>12}")
                continue
            if cross is None:
                print(f"  {curr:<8} {pdf_rate:>12.6f} {'N/A (no jcb.jp)':>12}")
                continue

            diff_pct = (cross - pdf_rate) / pdf_rate * 100
            all_diffs.append(abs(diff_pct))
            marker = " ✓" if abs(diff_pct) < 0.5 else " ✗"
            print(f"  {curr:<8} {pdf_rate:>12.6f} {cross:>12.6f} {diff_pct:>+8.3f}%{marker}")

        # Compute new currencies
        for curr in TARGET_CURRENCIES:
            cross = compute_cross_rate(raw, curr)
            if cross is not None:
                cross_rates_new[curr][date_str] = cross

    # Summary
    print("\n" + "=" * 70)
    if all_diffs:
        avg = sum(all_diffs) / len(all_diffs)
        mx = max(all_diffs)
        print(f"Verification summary: avg diff={avg:.3f}%  max diff={mx:.3f}%")
        if mx < 0.5:
            print("✓ Cross-rate is CONSISTENT with PDF rates (< 0.5% error)")
        elif mx < 2.0:
            print("~ Moderate difference — check if acceptable for your use case")
        else:
            print("✗ Large difference — jcb.jp and PDF may use different rate bases")

    # Show cross-rates for new currencies
    print(f"\nCross-rates for new currencies (TWD per unit):")
    print(f"  {'Date':<12} {'GBP':>10} {'AUD':>10} {'SGD':>10}")
    print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*10}")
    all_dates = sorted(set().union(*[c.keys() for c in cross_rates_new.values()]))
    for ds in all_dates:
        gbp = cross_rates_new["GBP"].get(ds)
        aud = cross_rates_new["AUD"].get(ds)
        sgd = cross_rates_new["SGD"].get(ds)
        row = f"  {ds:<12}"
        row += f" {gbp:>10.4f}" if gbp else f" {'N/A':>10}"
        row += f" {aud:>10.4f}" if aud else f" {'N/A':>10}"
        row += f" {sgd:>10.4f}" if sgd else f" {'N/A':>10}"
        print(row)


if __name__ == "__main__":
    main()
