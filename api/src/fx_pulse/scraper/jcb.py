"""JCB exchange rate scraper — cross-rate via jcb.jp HTML table.

Source: https://www.jcb.jp/rate/usd{MMDDYYYY}.html
Formula: TWD/currency = (TWD/USD sell) / (currency/USD buy)
"""

from __future__ import annotations

import logging
import random
import re
import time
from datetime import UTC, datetime

from curl_cffi import requests as cf_requests
from fake_useragent import UserAgent

from ..config import settings
from .base import CloudflareBlockedError, _IMPERSONATE_TARGETS, _check_cloudflare

logger = logging.getLogger(__name__)
_ua = UserAgent()

BASE_URL = "https://www.jcb.jp/rate/usd{date}.html"


class JcbScraper:
    """Scraper for JCB exchange rates via jcb.jp daily HTML table."""

    source_name = "JCB"

    def __init__(self) -> None:
        self._session: cf_requests.Session | None = None

    @property
    def session(self) -> cf_requests.Session:
        if self._session is None:
            target = random.choice(_IMPERSONATE_TARGETS)
            logger.debug("[%s] impersonate=%s", self.source_name, target)
            self._session = cf_requests.Session(impersonate=target)
            self._session.headers.update(
                {
                    "accept-language": "en-US,en;q=0.9",
                    "user-agent": _ua.random,
                }
            )
        return self._session

    # ── Public ────────────────────────────────────────────────────────────────

    def fetch_all(
        self,
        date: datetime | None = None,
        currencies: list[str] | None = None,
    ) -> dict[str, dict[str, float]]:
        """Fetch cross-rates for the given date.

        Returns: {"USD": {"rate": 31.588, "reverse": 0.031628}, ...}
        Raises ValueError if jcb.jp has no data for that date (404 / weekend).
        """
        if date is None:
            date = datetime.now(UTC)
        if currencies is None:
            currencies = settings.currencies

        logger.info("[%s] Fetching rates for %s", self.source_name, date.date())

        raw = self._fetch_raw_rates(date)
        result: dict[str, dict[str, float]] = {}

        for currency in currencies:
            if currency == "TWD":
                continue
            rate_data = self._compute_cross_rate(raw, currency)
            if rate_data is None:
                logger.warning("[%s] %s not found on jcb.jp", self.source_name, currency)
                continue
            result[currency] = rate_data
            logger.info(
                "[%s] %s/TWD | rate=%.10f reverse=%.6f",
                self.source_name,
                currency,
                rate_data["rate"],
                rate_data["reverse"],
            )

        logger.info("[%s] Fetch complete | %d currencies", self.source_name, len(result))
        return result

    def fetch_month(
        self,
        year: int,
        month: int,
        days: list[int],
        currencies: list[str] | None = None,
    ) -> dict[int, dict[str, dict[str, float]]]:
        """Fetch rates for multiple days in a month, one request per day.

        Returns: {1: {"USD": {"rate": ..., "reverse": ...}}, ...}
        Days with no data (404 / weekend) are omitted from the result.
        """
        if currencies is None:
            currencies = settings.currencies

        logger.info("[%s] Batch fetch | %04d-%02d | days=%s", self.source_name, year, month, days)

        result: dict[int, dict[str, dict[str, float]]] = {}
        for day in days:
            d = datetime(year, month, day, tzinfo=UTC)
            try:
                result[day] = self.fetch_all(date=d, currencies=currencies)
            except ValueError as exc:
                logger.warning("[%s] Day %d skipped: %s", self.source_name, day, exc)

        logger.info("[%s] Batch complete | %d days", self.source_name, len(result))
        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    def _fetch_raw_rates(self, date: datetime) -> dict[str, dict[str, float]]:
        """Fetch and parse jcb.jp table for the given date.

        Returns: {"JPY": {"buy": 158.96, "mid": 159.20, "sell": 159.45}, "TWD": {...}, ...}
        Raises ValueError on 404 (weekend / holiday / no data yet).
        """
        url = BASE_URL.format(date=date.strftime("%m%d%Y"))
        max_retries = settings.scraper_max_retries

        for attempt in range(max_retries):
            try:
                logger.info("[%s] GET %s", self.source_name, url)
                resp = self.session.get(url, timeout=settings.scraper_timeout)

                if resp.status_code == 404:
                    raise ValueError(f"[{self.source_name}] No rates for {date.date()} (404)")

                _check_cloudflare(resp)
                resp.raise_for_status()
                return self._parse_html(resp.text)

            except (ValueError, CloudflareBlockedError):
                raise  # 404 / CF block — don't retry
            except Exception as exc:
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"[{self.source_name}] Failed to fetch {url} after {max_retries} attempts"
                    ) from exc
                delay = random.uniform(0, min(settings.scraper_backoff_cap, 2**attempt))
                logger.warning(
                    "[%s] attempt %d/%d failed: %s — retry in %.1fs",
                    self.source_name,
                    attempt + 1,
                    max_retries,
                    exc,
                    delay,
                )
                self.session.headers["user-agent"] = _ua.random
                time.sleep(delay)

        raise RuntimeError("Unreachable")

    def _parse_html(self, html: str) -> dict[str, dict[str, float]]:
        """Parse rate table from jcb.jp HTML.

        Row format: <td>USD</td><td>=</td><td>buy</td><td>mid</td><td>sell</td><td>CURRENCY</td>
        Returns: {"JPY": {"buy": float, "mid": float, "sell": float}, ...}
        """
        result: dict[str, dict[str, float]] = {}

        # Match rows: USD = buy mid sell CURRENCY
        pattern = re.compile(
            r"<tr[^>]*>.*?"
            r"<td[^>]*>USD</td>\s*"
            r"<td[^>]*>=</td>\s*"
            r"<td[^>]*>([\d.]+)\s*</td>\s*"  # buy
            r"<td[^>]*>([\d.]+)\s*</td>\s*"  # mid
            r"<td[^>]*>([\d.]+)\s*</td>\s*"  # sell
            r"<td[^>]*>([A-Z]{3})</td>",
            re.DOTALL,
        )

        for m in pattern.finditer(html):
            buy, mid, sell, code = m.group(1), m.group(2), m.group(3), m.group(4)
            result[code] = {
                "buy": float(buy),
                "mid": float(mid),
                "sell": float(sell),
            }

        return result

    def _compute_cross_rate(
        self,
        raw: dict[str, dict[str, float]],
        currency: str,
    ) -> dict[str, float] | None:
        """Compute TWD/currency cross-rate.

        TWD/currency = (TWD/USD sell) / (currency/USD buy)
        """
        if "TWD" not in raw or currency not in raw:
            return None
        twd_sell = raw["TWD"]["sell"]
        currency_buy = raw[currency]["buy"]
        if currency_buy == 0:
            return None
        rate = twd_sell / currency_buy
        return {"rate": rate, "reverse": 1.0 / rate}
