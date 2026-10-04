"""Bounded retries shared by all rate sources."""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from ..config import settings


class PermanentHTTPError(RuntimeError):
    """A client error that must not be retried immediately."""


class RateLimitError(RuntimeError):
    """Stop this source until a later run, rather than ignoring Retry-After."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def check_http_status(response: Any) -> None:
    status = response.status_code
    if isinstance(status, int) and 400 <= status < 500 and status != 429:
        raise PermanentHTTPError(f"HTTP {status}: request rejected")


def retry_after_seconds(response: Any = None) -> float | None:
    """Parse the server's minimum wait, including HTTP-date headers."""
    header = response.headers.get("retry-after") if response is not None else None
    if not isinstance(header, str):
        return None
    try:
        seconds = float(header)
    except ValueError:
        try:
            deadline = parsedate_to_datetime(header)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            seconds = (deadline - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0, seconds) if math.isfinite(seconds) else None


def retry_delay(attempt: int, response: Any = None) -> float:
    """Full jitter with a Retry-After floor; never shorten the server's wait."""
    ceiling = min(settings.scraper_backoff_cap, settings.scraper_backoff_base * 2**attempt)
    delay = random.uniform(0, ceiling)
    seconds = retry_after_seconds(response)
    if seconds is None:
        return delay
    if seconds > settings.scraper_backoff_cap:
        raise RateLimitError(
            f"Retry-After {seconds:.0f}s exceeds in-process wait limit",
            retry_after_seconds=seconds,
        )
    return max(seconds, delay)
