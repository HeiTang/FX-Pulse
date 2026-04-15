"""Abstract store interface — all backends must implement this contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

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
