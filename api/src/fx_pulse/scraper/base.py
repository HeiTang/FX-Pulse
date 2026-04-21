"""Abstract base scraper — shared retry logic, logging, and interface contract.

All card network scrapers (VISA, Mastercard, JCB, ...) inherit from this class,
ensuring consistent behavior for retry, backoff, UA rotation, and logging.
"""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from curl_cffi import requests as cf_requests
from fake_useragent import UserAgent

from ..config import settings

logger = logging.getLogger(__name__)
_ua = UserAgent()

# Rotate across engines/versions — CF bot detection is fingerprint-aware.
# Only targets confirmed available in curl_cffi >= 0.7; chrome133 removed (unsupported).
_IMPERSONATE_TARGETS = [
    "chrome136",
    "safari18_0",
    "firefox135",
    "safari17_0",
    "chrome124",
]


class CloudflareBlockedError(RuntimeError):
    """Raised when a Cloudflare challenge/block is detected."""


def _check_cloudflare(resp: Any) -> None:
    """Raise CloudflareBlockedError if the response looks like a CF block."""
    if resp.status_code not in (403, 429, 503):
        return
    is_cf = (
        "cf-ray" in resp.headers
        or resp.headers.get("server", "").lower() == "cloudflare"
        or "cloudflare" in resp.text.lower()
        or "just a moment" in resp.text.lower()
    )
    if is_cf:
        raise CloudflareBlockedError(
            f"Cloudflare block: HTTP {resp.status_code} "
            f"(cf-ray: {resp.headers.get('cf-ray', 'n/a')})"
        )


class BaseScraper(ABC):
    """Base class for FX rate scrapers."""

    source_name: str  # "VISA", "Mastercard", "JCB"
    base_url: str
    referer: str

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
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                    "referer": self.referer,
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    "user-agent": _ua.random,
                }
            )
        return self._session

    # ── Abstract ───────────────────────────────────────────────────────────────

    @abstractmethod
    def _build_params(self, currency: str, date_str: str) -> dict[str, str]:
        """Build query parameters for a single currency request."""
        ...

    @abstractmethod
    def _parse_response(self, data: dict[str, Any]) -> dict[str, float]:
        """Extract {"rate": ..., "reverse": ...} from API response."""
        ...

    # ── Shared logic ───────────────────────────────────────────────────────────

    def fetch_one(
        self,
        currency: str,
        date_str: str,
    ) -> dict[str, float]:
        """Fetch a single currency pair with exponential backoff + full jitter."""
        max_retries = settings.scraper_max_retries

        for attempt in range(max_retries):
            try:
                params = self._build_params(currency, date_str)
                logger.info(
                    "[%s] GET %s | %s/TWD | params=%s",
                    self.source_name,
                    self.base_url,
                    currency,
                    params,
                )

                resp = self.session.get(
                    self.base_url,
                    params=params,
                    timeout=settings.scraper_timeout,
                )
                logger.info(
                    "[%s] %s/TWD | HTTP %d | %d bytes",
                    self.source_name,
                    currency,
                    resp.status_code,
                    len(resp.content),
                )
                _check_cloudflare(resp)
                resp.raise_for_status()

                data = resp.json()
                logger.debug("[%s] %s/TWD | raw response: %s", self.source_name, currency, data)

                result = self._parse_response(data)
                logger.info(
                    "[%s] %s/TWD | rate=%.10f reverse=%.6f",
                    self.source_name,
                    currency,
                    result["rate"],
                    result["reverse"],
                )
                return result

            except CloudflareBlockedError:
                raise  # don't retry CF blocks
            except Exception as exc:
                if attempt == max_retries - 1:
                    logger.error(
                        "[%s] %s/TWD | FAILED after %d attempts: %s",
                        self.source_name,
                        currency,
                        max_retries,
                        exc,
                    )
                    raise RuntimeError(
                        f"[{self.source_name}] Failed to fetch {currency}/TWD "
                        f"after {max_retries} attempts"
                    ) from exc

                delay = min(settings.scraper_backoff_cap, 1.0 * (2**attempt))
                sleep = random.uniform(0, delay)
                logger.warning(
                    "[%s] %s/TWD | attempt %d/%d failed: %s — retry in %.1fs",
                    self.source_name,
                    currency,
                    attempt + 1,
                    max_retries,
                    exc,
                    sleep,
                )
                # Reset session so next attempt picks a fresh impersonate target
                self._session = None
                time.sleep(sleep)

        raise RuntimeError("Unreachable")

    def fetch_all(
        self,
        date: datetime | None = None,
        currencies: list[str] | None = None,
    ) -> dict[str, dict[str, float]]:
        """Fetch rates for multiple currencies.

        Returns: {"USD": {"rate": 31.547, "reverse": 0.0317}, ...}
        """
        if date is None:
            date = datetime.now(UTC)
        if currencies is None:
            currencies = settings.currencies

        date_str = date.strftime("%m/%d/%Y")
        logger.info(
            "[%s] Starting batch fetch | date=%s | currencies=%s",
            self.source_name,
            date_str,
            currencies,
        )

        result: dict[str, dict[str, float]] = {}
        for currency in currencies:
            result[currency] = self.fetch_one(currency, date_str)
            time.sleep(random.uniform(settings.scraper_delay_min, settings.scraper_delay_max))

        logger.info("[%s] Batch complete | %d currencies fetched", self.source_name, len(result))
        return result
