"""Tests for JsonStore — file I/O, upsert, query."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from fx_pulse.models.rate import CurrencyRate
from fx_pulse.store.json_store import JsonStore


class TestJsonStore:
    def test_upsert_and_get_latest(self, tmp_path):
        path = tmp_path / "rates.json"
        store = JsonStore(path=path)

        rates = {
            "USD": CurrencyRate(rate=31.577, reverse=0.031668),
            "JPY": CurrencyRate(rate=0.1991, reverse=5.0223),
        }
        store.upsert_rates("2026-04-15", "VISA", rates)

        result = store.get_latest_rates("VISA")
        assert result is not None

        date_key, latest = result
        assert date_key == "2026-04-15"
        assert latest["USD"].rate == 31.577
        assert latest["JPY"].reverse == 5.0223

    def test_get_latest_returns_most_recent(self, tmp_path):
        path = tmp_path / "rates.json"
        store = JsonStore(path=path)

        old = {"USD": CurrencyRate(rate=30.0, reverse=0.033)}
        new = {"USD": CurrencyRate(rate=31.5, reverse=0.031)}

        store.upsert_rates("2026-04-14", "VISA", old)
        store.upsert_rates("2026-04-15", "VISA", new)

        date_key, latest = store.get_latest_rates("VISA")
        assert date_key == "2026-04-15"
        assert latest["USD"].rate == 31.5

    def test_get_latest_returns_none_when_empty(self, tmp_path):
        store = JsonStore(path=tmp_path / "empty.json")
        assert store.get_latest_rates("VISA") is None

    def test_get_latest_returns_none_for_unknown_source(self, tmp_path):
        path = tmp_path / "rates.json"
        store = JsonStore(path=path)

        rates = {"USD": CurrencyRate(rate=31.5, reverse=0.031)}
        store.upsert_rates("2026-04-15", "VISA", rates)

        assert store.get_latest_rates("Mastercard") is None

    def test_get_history_sorted_asc(self, tmp_path):
        path = tmp_path / "rates.json"
        store = JsonStore(path=path)

        for day in range(10, 16):
            rates = {"USD": CurrencyRate(rate=30.0 + day * 0.1, reverse=0.03)}
            store.upsert_rates(f"2026-04-{day}", "VISA", rates)

        points = store.get_history("USD", "VISA", days=3)
        assert len(points) == 3
        assert points[0].date < points[-1].date  # ASC order

    def test_get_history_filters_currency(self, tmp_path):
        path = tmp_path / "rates.json"
        store = JsonStore(path=path)

        rates = {
            "USD": CurrencyRate(rate=31.5, reverse=0.031),
            "JPY": CurrencyRate(rate=0.199, reverse=5.02),
        }
        store.upsert_rates("2026-04-15", "VISA", rates)

        points = store.get_history("JPY", "VISA", days=30)
        assert len(points) == 1
        assert points[0].rate == 0.199

    def test_export_payload(self, tmp_path):
        path = tmp_path / "rates.json"
        store = JsonStore(path=path)

        rates = {"USD": CurrencyRate(rate=31.5, reverse=0.031)}
        store.upsert_rates("2026-04-15", "VISA", rates)

        payload = store.export_payload()
        assert "2026-04-15" in payload.rates
        assert payload.meta.base == "TWD"

    def test_multiple_sources(self, tmp_path):
        path = tmp_path / "rates.json"
        store = JsonStore(path=path)

        visa = {"USD": CurrencyRate(rate=31.5, reverse=0.031)}
        mc = {"USD": CurrencyRate(rate=31.6, reverse=0.0316)}

        store.upsert_rates("2026-04-15", "VISA", visa)
        store.upsert_rates("2026-04-15", "Mastercard", mc)

        _, visa_rates = store.get_latest_rates("VISA")
        _, mc_rates = store.get_latest_rates("Mastercard")

        assert visa_rates["USD"].rate == 31.5
        assert mc_rates["USD"].rate == 31.6


class TestFindMissing:
    # 2026-04-21 = Tuesday, 2026-04-19 = Sunday, 2026-04-18 = Saturday

    def test_present_entry_not_reported(self, tmp_path):
        store = JsonStore(path=tmp_path / "rates.json")
        rates = {"USD": CurrencyRate(rate=31.5, reverse=0.031)}
        store.upsert_rates("2026-04-21", "VISA", rates)

        with patch("fx_pulse.store.base.datetime") as mock_dt:
            mock_dt.now.return_value.date.return_value = date(2026, 4, 21)
            missing = store.find_missing(["VISA"], days=1)

        assert missing == []

    def test_missing_source_reported(self, tmp_path):
        store = JsonStore(path=tmp_path / "rates.json")
        rates = {"USD": CurrencyRate(rate=31.5, reverse=0.031)}
        store.upsert_rates("2026-04-21", "VISA", rates)

        with patch("fx_pulse.store.base.datetime") as mock_dt:
            mock_dt.now.return_value.date.return_value = date(2026, 4, 21)
            missing = store.find_missing(["VISA", "Mastercard"], days=1)

        assert ("2026-04-21", "Mastercard") in missing
        assert ("2026-04-21", "VISA") not in missing

    def test_jcb_weekend_skipped(self, tmp_path):
        store = JsonStore(path=tmp_path / "rates.json")

        with patch("fx_pulse.store.base.datetime") as mock_dt:
            mock_dt.now.return_value.date.return_value = date(2026, 4, 19)  # Sunday
            missing = store.find_missing(["JCB"], days=1)

        assert missing == []

    def test_jcb_weekday_reported_when_missing(self, tmp_path):
        store = JsonStore(path=tmp_path / "rates.json")

        with patch("fx_pulse.store.base.datetime") as mock_dt:
            mock_dt.now.return_value.date.return_value = date(2026, 4, 21)  # Tuesday
            missing = store.find_missing(["JCB"], days=1)

        assert ("2026-04-21", "JCB") in missing

    def test_rolling_window_covers_past_days(self, tmp_path):
        store = JsonStore(path=tmp_path / "rates.json")
        rates = {"USD": CurrencyRate(rate=31.5, reverse=0.031)}
        store.upsert_rates("2026-04-21", "VISA", rates)

        with patch("fx_pulse.store.base.datetime") as mock_dt:
            mock_dt.now.return_value.date.return_value = date(2026, 4, 21)
            missing = store.find_missing(["VISA"], days=2)

        assert ("2026-04-20", "VISA") in missing
        assert ("2026-04-21", "VISA") not in missing
