"""Tests for FastAPI routes — mock store, verify HTTP responses."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from fx_pulse.main import app
from fx_pulse.models.rate import CurrencyRate, HistoryPoint

client = TestClient(app)

MOCK_RATES = {
    "USD": CurrencyRate(rate=31.577, reverse=0.031668),
    "JPY": CurrencyRate(rate=0.1991, reverse=5.0223),
}


class TestLatest:
    @patch("fx_pulse.routers.rates.get_store")
    def test_returns_latest_rates(self, mock_get_store):
        mock_store = mock_get_store.return_value
        mock_store.get_latest_rates.return_value = ("2026-04-15", MOCK_RATES)

        resp = client.get("/rates/latest")
        assert resp.status_code == 200

        data = resp.json()
        assert data["date"] == "2026-04-15"
        assert data["source"] == "VISA"
        assert data["rates"]["USD"]["rate"] == 31.577

    @patch("fx_pulse.routers.rates.get_store")
    def test_returns_404_when_no_data(self, mock_get_store):
        mock_store = mock_get_store.return_value
        mock_store.get_latest_rates.return_value = None

        resp = client.get("/rates/latest")
        assert resp.status_code == 404

    @patch("fx_pulse.routers.rates.get_store")
    def test_accepts_source_param(self, mock_get_store):
        mock_store = mock_get_store.return_value
        mock_store.get_latest_rates.return_value = ("2026-04-15", MOCK_RATES)

        resp = client.get("/rates/latest?source=Mastercard")
        assert resp.status_code == 200
        mock_store.get_latest_rates.assert_called_with("Mastercard")


class TestHistory:
    @patch("fx_pulse.routers.rates.get_store")
    def test_returns_history_points(self, mock_get_store):
        mock_store = mock_get_store.return_value
        mock_store.get_history.return_value = [
            HistoryPoint(date="2026-04-14", rate=31.5, reverse=0.0317),
            HistoryPoint(date="2026-04-15", rate=31.577, reverse=0.031668),
        ]

        resp = client.get("/rates/history/USD")
        assert resp.status_code == 200

        data = resp.json()
        assert data["currency"] == "USD"
        assert len(data["data"]) == 2
        assert data["data"][0]["date"] == "2026-04-14"

    @patch("fx_pulse.routers.rates.get_store")
    def test_rejects_unsupported_currency(self, mock_get_store):
        resp = client.get("/rates/history/XYZ")
        assert resp.status_code == 404
        assert "XYZ" in resp.json()["detail"]

    @patch("fx_pulse.routers.rates.get_store")
    def test_accepts_days_param(self, mock_get_store):
        mock_store = mock_get_store.return_value
        mock_store.get_history.return_value = []

        resp = client.get("/rates/history/USD?days=7")
        assert resp.status_code == 200
        mock_store.get_history.assert_called_with("USD", "VISA", 7)


class TestHealth:
    def test_health_endpoint(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
