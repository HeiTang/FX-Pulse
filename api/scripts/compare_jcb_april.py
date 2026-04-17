"""Compare new JCB scraper (jcb.jp) against existing rates.json for April 2026.

Fetches fresh data for all days in April that already exist in rates.json,
then prints a side-by-side comparison.

Usage:
    poetry run python scripts/compare_jcb_april.py
"""

from __future__ import annotations

import json
from pathlib import Path

from fx_pulse.scraper.jcb import JcbScraper

RATES_JSON = Path(__file__).parent.parent.parent / "web" / "src" / "data" / "rates.json"
CURRENCIES = ["JPY", "KRW", "USD", "HKD", "EUR"]  # existing 5 from PDF


def main() -> None:
    with open(RATES_JSON) as f:
        store = json.load(f)["rates"]

    existing_days = sorted(
        [d for d in store if d.startswith("2026-04") and "JCB" in store[d]]
    )
    day_nums = [int(d.split("-")[2]) for d in existing_days]

    print(f"Found {len(day_nums)} days with JCB data in rates.json")
    print(f"Days: {day_nums}\n")

    scraper = JcbScraper()
    print("Fetching from jcb.jp...\n")
    fresh = scraper.fetch_month(2026, 4, day_nums)

    # Compare
    print(f"{'Date':<12} {'Currency':<6} {'rates.json':>12} {'jcb.jp new':>12} {'Diff %':>8} {'Match'}")
    print("-" * 60)

    all_match = True
    for date_str in existing_days:
        day = int(date_str.split("-")[2])
        pdf_day = store[date_str]["JCB"]
        new_day = fresh.get(day, {})

        for curr in CURRENCIES:
            pdf_rate = pdf_day.get(curr, {}).get("rate")
            new_rate = new_day.get(curr, {}).get("rate")

            if pdf_rate is None and new_rate is None:
                continue
            if pdf_rate is None:
                print(f"{date_str:<12} {curr:<6} {'N/A (no PDF)':>12} {new_rate:>12.6f}        NEW")
                continue
            if new_rate is None:
                print(f"{date_str:<12} {curr:<6} {pdf_rate:>12.6f} {'N/A (404)':>12}        MISS")
                all_match = False
                continue

            diff = (new_rate - pdf_rate) / pdf_rate * 100
            match = "✓" if abs(diff) < 0.001 else "✗"
            if match == "✗":
                all_match = False
            print(f"{date_str:<12} {curr:<6} {pdf_rate:>12.6f} {new_rate:>12.6f} {diff:>+8.4f}% {match}")

    print("\n" + "=" * 60)
    if all_match:
        print("✓ All values match. New scraper is consistent with existing rates.json.")
    else:
        print("✗ Discrepancies found. Check above.")

    # Also show new currencies not previously in rates.json
    print("\nNew currencies now available (GBP, AUD, SGD):")
    print(f"{'Date':<12} {'GBP':>10} {'AUD':>10} {'SGD':>10}")
    print("-" * 45)
    for date_str in existing_days:
        day = int(date_str.split("-")[2])
        new_day = fresh.get(day, {})
        gbp = new_day.get("GBP", {}).get("rate")
        aud = new_day.get("AUD", {}).get("rate")
        sgd = new_day.get("SGD", {}).get("rate")
        row = f"{date_str:<12}"
        row += f" {gbp:>10.4f}" if gbp else f" {'N/A':>10}"
        row += f" {aud:>10.4f}" if aud else f" {'N/A':>10}"
        row += f" {sgd:>10.4f}" if sgd else f" {'N/A':>10}"
        print(row)


if __name__ == "__main__":
    main()
