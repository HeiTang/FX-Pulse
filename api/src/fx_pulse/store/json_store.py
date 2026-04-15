"""JSON file storage backend."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..config import settings
from ..models.rate import CurrencyRate, HistoryPoint, RatesPayload
from .base import BaseStore, SourceRates


class JsonStore(BaseStore):
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or settings.data_file

    def _load(self) -> RatesPayload:
        if not self._path.exists():
            return RatesPayload(
                meta={
                    "base": settings.base_currency,
                    "currencies": settings.currencies,
                    "last_updated": "",
                },
                rates={},
            )
        with self._path.open() as f:
            return RatesPayload.model_validate(json.load(f))

    def _save(self, payload: RatesPayload) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w") as f:
            json.dump(payload.model_dump(), f, ensure_ascii=False, indent=2)

    # ── Interface ──────────────────────────────────────────────────────────────

    def upsert_rates(self, date_key: str, source: str, rates: SourceRates) -> None:
        payload = self._load()
        payload.rates.setdefault(date_key, {})
        payload.rates[date_key][source] = rates
        payload.meta.last_updated = datetime.now(UTC).isoformat()
        self._save(payload)

    def get_latest_rates(self, source: str) -> tuple[str, SourceRates] | None:
        payload = self._load()
        if not payload.rates:
            return None

        # Walk dates descending until we find one with this source
        for date_key in sorted(payload.rates, reverse=True):
            source_rates = payload.rates[date_key].get(source)
            if source_rates:
                parsed = {
                    k: CurrencyRate(**v) if isinstance(v, dict) else v
                    for k, v in source_rates.items()
                }
                return (date_key, parsed)
        return None

    def get_history(self, currency: str, source: str, days: int) -> list[HistoryPoint]:
        payload = self._load()
        currency = currency.upper()

        sorted_dates = sorted(payload.rates, reverse=True)[:days]
        points: list[HistoryPoint] = []

        for date_key in sorted_dates:
            source_rates = payload.rates[date_key].get(source, {})
            entry = source_rates.get(currency)
            if entry:
                rate_data = entry if isinstance(entry, dict) else entry.model_dump()
                points.append(HistoryPoint(date=date_key, **rate_data))

        return sorted(points, key=lambda p: p.date)

    def export_payload(self) -> RatesPayload:
        return self._load()
