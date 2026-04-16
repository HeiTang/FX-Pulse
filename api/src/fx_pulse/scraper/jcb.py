"""JCB exchange rate scraper — PDF download + table parsing."""

from __future__ import annotations

import logging
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pdfplumber
from curl_cffi import requests as cf_requests
from fake_useragent import UserAgent

from ..config import settings

logger = logging.getLogger(__name__)
_ua = UserAgent()

LISTING_URL = "https://www.specialoffers.jcb/zh-tw/services/other/rate/"
BASE_URL = "https://www.specialoffers.jcb"


class JcbScraper:
    """Scraper for JCB exchange rates published as monthly PDFs."""

    source_name = "JCB"

    def __init__(self) -> None:
        self._session: cf_requests.Session | None = None

    @property
    def session(self) -> cf_requests.Session:
        if self._session is None:
            self._session = cf_requests.Session(impersonate="chrome120")
            self._session.headers.update(
                {
                    "accept-language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
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
        """Download the current month's PDF and parse today's rates.

        Returns: {"USD": {"rate": 31.617, "reverse": 0.031628}, ...}
        Only returns currencies present in both the PDF and *currencies* list.
        """
        if date is None:
            date = datetime.now(UTC)
        if currencies is None:
            currencies = settings.currencies

        year, month, day = date.year, date.month, date.day

        logger.info(
            "[%s] Starting fetch | target=%04d-%02d-%02d",
            self.source_name,
            year,
            month,
            day,
        )

        pdf_url = self._find_pdf_url(year, month)
        pdf_path = self._download_pdf(pdf_url)

        try:
            all_rates = self._parse_pdf(pdf_path, day)
        finally:
            pdf_path.unlink(missing_ok=True)

        # Filter to tracked currencies only
        tracked = set(currencies)
        result = {k: v for k, v in all_rates.items() if k in tracked}

        logger.info(
            "[%s] Fetch complete | %d currencies extracted",
            self.source_name,
            len(result),
        )
        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    def _find_pdf_url(self, year: int, month: int) -> str:
        """Scrape listing page to find the PDF URL for the given month."""
        logger.info("[%s] Fetching listing page: %s", self.source_name, LISTING_URL)

        resp = self.session.get(LISTING_URL, timeout=settings.scraper_timeout)
        resp.raise_for_status()
        html = resp.text

        # Match: <a href="/zh-tw/services/...pdf">2026年4月</a>
        target_label = f"{year}年{month}月"
        pattern = r'href="([^"]+\.pdf)"[^>]*>\s*' + re.escape(target_label)
        match = re.search(pattern, html)

        if not match:
            raise ValueError(f"[{self.source_name}] PDF not found for {target_label}")

        pdf_path = match.group(1)
        url = pdf_path if pdf_path.startswith("http") else BASE_URL + pdf_path
        logger.info("[%s] Found PDF: %s", self.source_name, url)
        return url

    def _download_pdf(self, url: str) -> Path:
        """Download PDF to a temporary file."""
        logger.info("[%s] Downloading PDF: %s", self.source_name, url)

        resp = self.session.get(url, timeout=settings.scraper_timeout)
        resp.raise_for_status()

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(resp.content)
        tmp.close()

        logger.info(
            "[%s] PDF saved: %s (%d bytes)",
            self.source_name,
            tmp.name,
            len(resp.content),
        )
        return Path(tmp.name)

    def _parse_pdf(
        self,
        path: Path,
        target_day: int,
    ) -> dict[str, dict[str, float]]:
        """Parse all pages, find the target day row, extract rates."""
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    result = self._extract_from_table(table, target_day)
                    if result is not None:
                        return result

        raise ValueError(f"[{self.source_name}] No rate data found for day {target_day}")

    def _extract_from_table(
        self,
        table: list[list[Any]],
        target_day: int,
    ) -> dict[str, dict[str, float]] | None:
        """Try to extract rates for target_day from a single table.

        Returns None if the target day is not in this table.
        """
        if len(table) < 3:
            return None

        # Row 0 = header with currency codes: ['4月', 'JPY', 'KRW', 'USD', ...]
        header = table[0]
        currency_cols = {i: header[i] for i in range(1, len(header))}

        # Row 2+ = data rows: ['16日', '0.1993973', '0.0215425', ...]
        day_label = f"{target_day}日"

        for row in table[2:]:
            if not row or row[0] != day_label:
                continue

            # Check if this row has data (not empty future dates)
            if not row[1] or row[1].strip() == "":
                logger.warning(
                    "[%s] Day %d found but no data yet",
                    self.source_name,
                    target_day,
                )
                return None

            result: dict[str, dict[str, float]] = {}
            for col_idx, currency in currency_cols.items():
                val = row[col_idx] if col_idx < len(row) else ""
                if not val or val.strip() == "":
                    continue
                rate = float(val)
                if rate <= 0:
                    continue
                reverse = 1.0 / rate
                result[currency] = {"rate": rate, "reverse": reverse}

                logger.info(
                    "[%s] %s/TWD | rate=%.10f reverse=%.6f",
                    self.source_name,
                    currency,
                    rate,
                    reverse,
                )

            return result

        return None
