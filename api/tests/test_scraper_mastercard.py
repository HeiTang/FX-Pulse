"""Tests for Mastercard scraper — parse, params, retry."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from fx_pulse.scraper.mastercard import MastercardScraper

MOCK_MC_RESPONSE = {
    "data": {
        "conversionRate": "0.1992753",
        "crdhldBillAmt": "0.1992753",
        "crdhldBillCurr": "TWD",
        "fxDate": "2026-04-15",
        "transAmt": "1",
        "transCurr": "JPY",
    }
}


class TestMastercardScraperParse:
    def test_parse_response_extracts_rate_and_reverse(self):
        scraper = MastercardScraper()
        result = scraper._parse_response(MOCK_MC_RESPONSE)

        assert result["rate"] == 0.1992753
        assert result["reverse"] == pytest.approx(1.0 / 0.1992753)

    def test_parse_response_rejects_missing_data(self):
        scraper = MastercardScraper()
        with pytest.raises(ValueError, match="missing"):
            scraper._parse_response({})

    def test_parse_response_rejects_zero_rate(self):
        scraper = MastercardScraper()
        bad = {"data": {"conversionRate": "0"}}
        with pytest.raises(ValueError, match="Invalid"):
            scraper._parse_response(bad)


class TestMastercardScraperParams:
    def test_build_params_converts_date_format(self):
        scraper = MastercardScraper()
        params = scraper._build_params("JPY", "04/15/2026")

        assert params["exchange_date"] == "2026-04-15"

    def test_build_params_sets_twd_as_billing(self):
        scraper = MastercardScraper()
        params = scraper._build_params("USD", "04/15/2026")

        assert params["cardholder_billing_currency"] == "TWD"
        assert params["transaction_currency"] == "USD"
        assert params["transaction_amount"] == "1"
        assert params["bank_fee"] == "0"


class TestMastercardFetchOneRetry:
    def _make_scraper_with_mock_session(self):
        scraper = MastercardScraper()
        mock_session = MagicMock()
        # Patch the property so _session = None resets don't break the mock
        type(scraper).session = PropertyMock(return_value=mock_session)
        return scraper, mock_session

    def test_fetch_one_retries_on_failure(self):
        scraper, mock_session = self._make_scraper_with_mock_session()

        mock_resp_fail = MagicMock()
        mock_resp_fail.raise_for_status.side_effect = RuntimeError("403 Forbidden")

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.content = b"{}"
        mock_resp_ok.raise_for_status.return_value = None
        mock_resp_ok.json.return_value = MOCK_MC_RESPONSE

        mock_session.get.side_effect = [mock_resp_fail, mock_resp_ok]

        with patch("fx_pulse.scraper.base.time.sleep"):
            result = scraper.fetch_one("JPY", "04/15/2026")

        assert result["rate"] == 0.1992753
        assert mock_session.get.call_count == 2

    def test_fetch_one_raises_after_max_retries(self):
        scraper, mock_session = self._make_scraper_with_mock_session()

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = RuntimeError("Server down")
        mock_session.get.return_value = mock_resp

        with (
            patch("fx_pulse.scraper.base.time.sleep"),
            pytest.raises(RuntimeError, match="Failed to fetch JPY/TWD"),
        ):
            scraper.fetch_one("JPY", "04/15/2026")
