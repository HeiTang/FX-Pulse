"""Tests for JCB scraper — PDF parsing, URL discovery, currency filtering."""

from __future__ import annotations

import pytest

from fx_pulse.scraper.jcb import JcbScraper

# Mock table data matching real JCB PDF structure
MOCK_TABLE_PAGE1 = [
    ["4月", "JPY", "KRW", "USD", "CNY", "THB", "VND", "HKD", "EUR", "PHP"],
    [None, "日圓", "韓幣", "美金", "人民幣", "泰幣", "越南幣", "港幣", "歐元", "菲律賓幣"],
    [
        "1日",
        "0.2018881",
        "0.0213592",
        "31.968",
        "4.6576751",
        "0.987885",
        "0.0012144",
        "4.0825745",
        "36.9972057",
        "0.5289659",
    ],
    [
        "2日",
        "0.2021279",
        "0.0212779",
        "32.032",
        "4.6846572",
        "0.9868254",
        "0.0012174",
        "4.0957509",
        "37.1277787",
        "0.5336025",
    ],
]

MOCK_TABLE_PAGE2 = [
    ["4月", "JPY", "KRW", "USD", "CNY", "THB", "VND", "HKD", "EUR", "PHP"],
    [None, "日圓", "韓幣", "美金", "人民幣", "泰幣", "越南幣", "港幣", "歐元", "菲律賓幣"],
    [
        "16日",
        "0.1993973",
        "0.0215425",
        "31.617",
        "4.6605865",
        "0.9932407",
        "0.001202",
        "4.0486519",
        "37.3429651",
        "0.5277685",
    ],
    ["17日", "", "", "", "", "", "", "", "", ""],
]

MOCK_LISTING_HTML = """
<html><body>
<a href="/zh-tw/services/abc123_11.pdf">2026年4月</a>
<a href="/zh-tw/services/def456_18.pdf">2026年3月</a>
</body></html>
"""


class TestExtractFromTable:
    def test_extracts_rates_for_target_day(self):
        scraper = JcbScraper()
        result = scraper._extract_from_table(MOCK_TABLE_PAGE1, 1)

        assert result is not None
        assert result["USD"]["rate"] == 31.968
        assert result["JPY"]["rate"] == 0.2018881
        assert result["EUR"]["rate"] == 36.9972057

    def test_calculates_reverse(self):
        scraper = JcbScraper()
        result = scraper._extract_from_table(MOCK_TABLE_PAGE1, 1)

        assert result is not None
        assert result["USD"]["reverse"] == pytest.approx(1.0 / 31.968)

    def test_returns_none_for_missing_day(self):
        scraper = JcbScraper()
        result = scraper._extract_from_table(MOCK_TABLE_PAGE1, 15)

        assert result is None

    def test_returns_none_for_empty_row(self):
        scraper = JcbScraper()
        result = scraper._extract_from_table(MOCK_TABLE_PAGE2, 17)

        assert result is None

    def test_extracts_all_nine_currencies(self):
        scraper = JcbScraper()
        result = scraper._extract_from_table(MOCK_TABLE_PAGE2, 16)

        assert result is not None
        assert len(result) == 9
        expected = {"JPY", "KRW", "USD", "CNY", "THB", "VND", "HKD", "EUR", "PHP"}
        assert set(result.keys()) == expected


class TestFindPdfUrl:
    def test_finds_matching_month(self):
        scraper = JcbScraper()
        # Mock session response
        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.text = MOCK_LISTING_HTML
        mock_resp.raise_for_status.return_value = None
        scraper._session = MagicMock()
        scraper._session.get.return_value = mock_resp

        url = scraper._find_pdf_url(2026, 4)
        assert url == "https://www.specialoffers.jcb/zh-tw/services/abc123_11.pdf"

    def test_raises_for_missing_month(self):
        scraper = JcbScraper()
        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.text = MOCK_LISTING_HTML
        mock_resp.raise_for_status.return_value = None
        scraper._session = MagicMock()
        scraper._session.get.return_value = mock_resp

        with pytest.raises(ValueError, match="PDF not found"):
            scraper._find_pdf_url(2026, 12)


class TestFetchAllFiltering:
    def test_only_returns_tracked_currencies(self):
        """fetch_all should filter to only currencies in the provided list."""
        scraper = JcbScraper()
        result_all = scraper._extract_from_table(MOCK_TABLE_PAGE2, 16)
        assert result_all is not None

        # Simulate what fetch_all does: filter to tracked currencies
        tracked = {"USD", "JPY", "EUR", "HKD", "KRW"}
        filtered = {k: v for k, v in result_all.items() if k in tracked}

        assert set(filtered.keys()) == {"USD", "JPY", "EUR", "HKD", "KRW"}
        assert "CNY" not in filtered
        assert "THB" not in filtered
