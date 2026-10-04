"""JSON file storage backend."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile

from ..config import settings
from ..models.rate import HistoryPoint, RatesPayload
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
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=".rates-",
                suffix=".tmp",
                delete=False,
            ) as f:
                temporary = Path(f.name)
                json.dump(payload.model_dump(), f, ensure_ascii=False, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            temporary.replace(self._path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    # ── Interface ──────────────────────────────────────────────────────────────

    def upsert_rates(self, date_key: str, source: str, rates: SourceRates) -> None:
        if date.fromisoformat(date_key).isoformat() != date_key:
            raise ValueError("Expected date key YYYY-MM-DD")
        if not source or not rates:
            raise ValueError("Cannot store an empty source or rate set")
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
                return (date_key, source_rates)
        return None

    def get_history(self, currency: str, source: str, days: int) -> list[HistoryPoint]:
        payload = self._load()
        currency = currency.upper()

        if days < 1 or not payload.rates:
            return []
        latest = date.fromisoformat(max(payload.rates))
        first = (latest - timedelta(days=days - 1)).isoformat()
        sorted_dates = [key for key in sorted(payload.rates) if key >= first]
        points: list[HistoryPoint] = []

        for date_key in sorted_dates:
            source_rates = payload.rates[date_key].get(source, {})
            entry = source_rates.get(currency)
            if entry:
                points.append(HistoryPoint(date=date_key, **entry.model_dump()))

        return sorted(points, key=lambda p: p.date)

    def export_payload(self) -> RatesPayload:
        return self._load()
