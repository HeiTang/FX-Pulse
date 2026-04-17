"""Tests for JCB scraper — HTML parsing, cross-rate calculation, filtering."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fx_pulse.scraper.jcb import JcbScraper

# Minimal HTML fixture matching jcb.jp table structure
MOCK_HTML = """
<html><body>
<table class="CSVTable"><tbody>
<tr class="odd"><td></td><td></td><td>Buy</td><td>Mid</td><td>Sell</td><td></td></tr>
<tr class="even"><td>USD</td><td>=</td><td>158.959200000</td><td>159.203000000</td><td>159.446800000</td><td>JPY</td></tr><tr class="odd"><td>USD</td><td>=</td><td>1471.465700000</td><td>1475.232850000</td><td>1479.000000000</td><td>KRW</td></tr><tr class="even"><td>USD</td><td>=</td><td>0.848597480</td><td>0.848852478</td><td>0.849107630</td><td>EUR</td></tr><tr class="odd"><td>USD</td><td>=</td><td>0.739297194</td><td>0.739379187</td><td>0.739460652</td><td>GBP</td></tr><tr class="even"><td>USD</td><td>=</td><td>7.812879000</td><td>7.824779000</td><td>7.836679000</td><td>HKD</td></tr><tr class="odd"><td>USD</td><td>=</td><td>1.395893560</td><td>1.396899720</td><td>1.397907332</td><td>AUD</td></tr><tr class="even"><td>USD</td><td>=</td><td>1.270829000</td><td>1.273193000</td><td>1.275557000</td><td>SGD</td></tr><tr class="odd"><td>USD</td><td>=</td><td>31.400210000</td><td>31.494105000</td><td>31.588000000</td><td>TWD</td></tr></tbody></table>
</body></html>
"""

# Expected parsed rates from MOCK_HTML
EXPECTED_RAW = {
    "JPY": {"buy": 158.9592, "mid": 159.203, "sell": 159.4468},
    "KRW": {"buy": 1471.4657, "mid": 1475.23285, "sell": 1479.0},
    "EUR": {"buy": 0.84859748, "mid": 0.848852478, "sell": 0.84910763},
    "GBP": {"buy": 0.739297194, "mid": 0.739379187, "sell": 0.739460652},
    "HKD": {"buy": 7.812879, "mid": 7.824779, "sell": 7.836679},
    "AUD": {"buy": 1.39589356, "mid": 1.39689972, "sell": 1.397907332},
    "SGD": {"buy": 1.270829, "mid": 1.273193, "sell": 1.275557},
    "TWD": {"buy": 31.40021, "mid": 31.494105, "sell": 31.588},
}

TWD_SELL = 31.588


class TestParseHtml:
    def test_parses_all_currencies(self):
        scraper = JcbScraper()
        result = scraper._parse_html(MOCK_HTML)
        assert set(result.keys()) == {"JPY", "KRW", "EUR", "GBP", "HKD", "AUD", "SGD", "TWD"}

    def test_parses_buy_mid_sell(self):
        scraper = JcbScraper()
        result = scraper._parse_html(MOCK_HTML)
        assert result["JPY"]["buy"] == pytest.approx(158.9592)
        assert result["JPY"]["mid"] == pytest.approx(159.203)
        assert result["JPY"]["sell"] == pytest.approx(159.4468)

    def test_parses_twd(self):
        scraper = JcbScraper()
        result = scraper._parse_html(MOCK_HTML)
        assert result["TWD"]["sell"] == pytest.approx(31.588)

    def test_returns_empty_on_no_table(self):
        scraper = JcbScraper()
        result = scraper._parse_html("<html><body>No table here</body></html>")
        assert result == {}


class TestComputeCrossRate:
    def test_jpy_matches_known_pdf_rate(self):
        scraper = JcbScraper()
        result = scraper._compute_cross_rate(EXPECTED_RAW, "JPY")
        assert result is not None
        # Known PDF rate for 2026-04-17: 0.1987176
        assert result["rate"] == pytest.approx(TWD_SELL / 158.9592, rel=1e-6)
        assert result["reverse"] == pytest.approx(1.0 / result["rate"])

    def test_gbp_cross_rate(self):
        scraper = JcbScraper()
        result = scraper._compute_cross_rate(EXPECTED_RAW, "GBP")
        assert result is not None
        assert result["rate"] == pytest.approx(TWD_SELL / 0.739297194, rel=1e-6)

    def test_returns_none_when_currency_missing(self):
        scraper = JcbScraper()
        result = scraper._compute_cross_rate(EXPECTED_RAW, "XYZ")
        assert result is None

    def test_returns_none_when_twd_missing(self):
        scraper = JcbScraper()
        raw_no_twd = {k: v for k, v in EXPECTED_RAW.items() if k != "TWD"}
        result = scraper._compute_cross_rate(raw_no_twd, "JPY")
        assert result is None

    def test_reverse_is_reciprocal(self):
        scraper = JcbScraper()
        result = scraper._compute_cross_rate(EXPECTED_RAW, "EUR")
        assert result is not None
        assert result["reverse"] == pytest.approx(1.0 / result["rate"])


class TestFetchAll:
    def _mock_scraper(self, html: str = MOCK_HTML) -> JcbScraper:
        scraper = JcbScraper()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.raise_for_status.return_value = None
        scraper._session = MagicMock()
        scraper._session.get.return_value = mock_resp
        return scraper

    def test_returns_all_tracked_currencies(self):
        scraper = self._mock_scraper()
        result = scraper.fetch_all(currencies=["JPY", "EUR", "GBP", "AUD", "SGD", "KRW", "HKD"])
        assert set(result.keys()) == {"JPY", "EUR", "GBP", "AUD", "SGD", "KRW", "HKD"}

    def test_rate_and_reverse_present(self):
        scraper = self._mock_scraper()
        result = scraper.fetch_all(currencies=["JPY"])
        assert "rate" in result["JPY"]
        assert "reverse" in result["JPY"]

    def test_raises_on_404(self):
        scraper = JcbScraper()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        scraper._session = MagicMock()
        scraper._session.get.return_value = mock_resp
        with pytest.raises(ValueError, match="404"):
            scraper.fetch_all()

    def test_skips_missing_currency(self):
        scraper = self._mock_scraper()
        # CNY is not in mock HTML
        result = scraper.fetch_all(currencies=["JPY", "CNY"])
        assert "JPY" in result
        assert "CNY" not in result


class TestFetchMonth:
    def test_skips_days_with_no_data(self):
        scraper = JcbScraper()

        def side_effect(date, currencies):
            if date.day == 13:  # simulate weekend
                raise ValueError("404")
            return {"JPY": {"rate": 0.199, "reverse": 5.025}}

        with patch.object(scraper, "fetch_all", side_effect=side_effect):
            result = scraper.fetch_month(2026, 4, [12, 13, 14])

        assert 12 in result
        assert 13 not in result
        assert 14 in result
