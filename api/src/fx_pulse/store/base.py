"""Abstract store interface — all backends must implement this contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta

from ..models.rate import CurrencyRate, HistoryPoint, RatesPayload

# Type alias: {"USD": CurrencyRate(...), "JPY": CurrencyRate(...)}
SourceRates = dict[str, CurrencyRate]


class BaseStore(ABC):
    """Storage backend interface.

    Implementations: JsonStore (file), TursoStore (libSQL), D1Store (Cloudflare).
    """

    @abstractmethod
    def upsert_rates(self, date_key: str, source: str, rates: SourceRates) -> None:
        """Write or overwrite rates for a given date and source."""
        ...

    @abstractmethod
    def get_latest_rates(self, source: str) -> tuple[str, SourceRates] | None:
        """Return (date_key, rates) for the most recent entry of a source.

        Returns None if no data exists.
        """
        ...

    @abstractmethod
    def get_history(self, currency: str, source: str, days: int) -> list[HistoryPoint]:
        """Return up to `days` historical data points for a currency+source, sorted by date ASC."""
        ...

    @abstractmethod
    def export_payload(self) -> RatesPayload:
        """Dump full dataset as RatesPayload — used for Astro static build (rates.json)."""
        ...

    def find_missing(self, sources: list[str], days: int = 7) -> list[tuple[str, str]]:
        """Return (date_key, source) pairs absent from the last `days` days.

        JCB is skipped on weekends — jcb.jp does not publish Saturday/Sunday rates.
        Days are counted backwards from today (inclusive).
        """
        today = date.today()
        payload = self.export_payload()
        missing: list[tuple[str, str]] = []

        for i in range(days):
            d = today - timedelta(days=i)
            date_key = d.isoformat()
            for source in sources:
                if source.lower() == "jcb" and d.weekday() >= 5:  # Sat=5, Sun=6
                    continue
                existing = payload.rates.get(date_key, {})
                if not existing.get(source):
                    missing.append((date_key, source))

        return missing
