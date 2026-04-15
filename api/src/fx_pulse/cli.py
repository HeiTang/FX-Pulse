"""CLI entrypoint for FX Pulse scraper."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime

from .models.rate import CurrencyRate
from .scraper.visa import VisaScraper
from .store import get_store


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def main() -> None:
    _setup_logging()

    now = datetime.now(UTC)
    date_key = now.strftime("%Y-%m-%d")

    scraper = VisaScraper()
    raw = scraper.fetch_all(now)

    rates = {currency: CurrencyRate(**values) for currency, values in raw.items()}

    store = get_store()
    store.upsert_rates(date_key, scraper.source_name, rates)
