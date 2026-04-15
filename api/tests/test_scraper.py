"""Tests for scraper — mock HTTP, verify parsing and retry logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fx_pulse.scraper.visa import VisaScraper

# Captured from real VISA API response
MOCK_VISA_RESPONSE = {
    "originalValues": {
        "fromCurrency": "USD",
        "fromCurrencyName": "United States Dollar",
        "toCurrency": "TWD",
        "toCurrencyName": "New Taiwan Dollar",
        "asOfDate": 1776211200,
        "fromAmount": "1",
        "toAmountWithVisaRate": "31.577",
        "toAmountWithAdditionalFee": "31.577",
        "fxRateVisa": "31.577",
        "fxRateWithAdditionalFee": "31.577",
        "lastUpdatedVisaRate": 1776210625,
        "benchmarks": [],
    },
    "conversionAmountValue": "1",
    "conversionBankFee": "0.0",
    "conversionInputDate": "04/15/2026",
    "conversionFromCurrency": "TWD",
    "conversionToCurrency": "USD",
    "fromCurrencyName": "United States Dollar",
    "toCurrencyName": "New Taiwan Dollar",
    "convertedAmount": "31.577000",
    "benchMarkAmount": "",
    "fxRateWithAdditionalFee": "31.577",
    "reverseAmount": "0.031668",
    "disclaimerDate": "April 15, 2026",
    "status": "success",
}


class TestVisaScraperParse:
    def test_parse_response_extracts_rate_and_reverse(self):
        scraper = VisaScraper()
        result = scraper._parse_response(MOCK_VISA_RESPONSE)

        assert result["rate"] == 31.577
        assert result["reverse"] == 0.031668

    def test_parse_response_rejects_non_success(self):
        scraper = VisaScraper()
        bad_response = {**MOCK_VISA_RESPONSE, "status": "error"}

        with pytest.raises(ValueError, match="non-success"):
            scraper._parse_response(bad_response)


class TestVisaScraperParams:
    def test_build_params_uses_twd_as_from(self):
        scraper = VisaScraper()
        params = scraper._build_params("USD", "04/15/2026")

        assert params["fromCurr"] == "TWD"
        assert params["toCurr"] == "USD"
        assert params["amount"] == "1"
        assert params["exchangedate"] == "04/15/2026"


class TestFetchOneRetry:
    def _make_scraper_with_mock_session(self) -> tuple[VisaScraper, MagicMock]:
        scraper = VisaScraper()
        mock_session = MagicMock()
        scraper._session = mock_session  # bypass property, inject directly
        return scraper, mock_session

    def test_fetch_one_retries_on_failure(self):
        scraper, mock_session = self._make_scraper_with_mock_session()

        mock_resp_fail = MagicMock()
        mock_resp_fail.raise_for_status.side_effect = RuntimeError("Connection refused")

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.content = b"{}"
        mock_resp_ok.raise_for_status.return_value = None
        mock_resp_ok.json.return_value = MOCK_VISA_RESPONSE

        mock_session.get.side_effect = [mock_resp_fail, mock_resp_ok]

        with patch("fx_pulse.scraper.base.time.sleep"):
            result = scraper.fetch_one("USD", "04/15/2026")

        assert result["rate"] == 31.577
        assert mock_session.get.call_count == 2

    def test_fetch_one_raises_after_max_retries(self):
        scraper, mock_session = self._make_scraper_with_mock_session()

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = RuntimeError("Server down")
        mock_session.get.return_value = mock_resp

        with (
            patch("fx_pulse.scraper.base.time.sleep"),
            pytest.raises(RuntimeError, match="Failed to fetch USD/TWD"),
        ):
            scraper.fetch_one("USD", "04/15/2026")
