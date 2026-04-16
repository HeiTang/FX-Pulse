"""Tests for CLI entrypoint — option parsing, source filtering, date resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from fx_pulse.cli import _resolve_dates, _resolve_scrapers, main
from fx_pulse.scraper.jcb import JcbScraper
from fx_pulse.scraper.mastercard import MastercardScraper
from fx_pulse.scraper.visa import VisaScraper


class TestResolveScrapers:
    def test_default_returns_all_three(self):
        scrapers = _resolve_scrapers(None)
        assert len(scrapers) == 3
        assert isinstance(scrapers[0], VisaScraper)
        assert isinstance(scrapers[1], MastercardScraper)
        assert isinstance(scrapers[2], JcbScraper)

    def test_single_source(self):
        scrapers = _resolve_scrapers("VISA")
        assert len(scrapers) == 1
        assert isinstance(scrapers[0], VisaScraper)

    def test_multiple_sources(self):
        scrapers = _resolve_scrapers("visa,JCB")
        assert len(scrapers) == 2
        assert isinstance(scrapers[0], VisaScraper)
        assert isinstance(scrapers[1], JcbScraper)

    def test_case_insensitive(self):
        scrapers = _resolve_scrapers("mastercard")
        assert len(scrapers) == 1
        assert isinstance(scrapers[0], MastercardScraper)

    def test_invalid_source_raises(self):
        from click import BadParameter

        with pytest.raises(BadParameter, match="Unknown source 'AMEX'"):
            _resolve_scrapers("AMEX")


class TestResolveDates:
    def test_default_returns_today(self):
        dates = _resolve_dates(None, None, None, None)
        assert len(dates) == 1
        assert dates[0].date() == datetime.now(UTC).date()

    def test_single_date(self):
        dates = _resolve_dates("2026-04-15", None, None, None)
        assert len(dates) == 1
        assert dates[0] == datetime(2026, 4, 15, tzinfo=UTC)

    def test_month_expansion(self):
        dates = _resolve_dates(None, "2026-03", None, None)
        assert len(dates) == 31
        assert dates[0] == datetime(2026, 3, 1, tzinfo=UTC)
        assert dates[-1] == datetime(2026, 3, 31, tzinfo=UTC)

    def test_month_capped_at_today(self):
        """Future month dates should be capped at today."""
        dates = _resolve_dates(None, "2099-01", None, None)
        # Should only return dates up to today, which is before 2099
        # So it will return today's date since 2099-01-01 > today
        assert len(dates) == 0 or dates[-1].date() <= datetime.now(UTC).date()

    def test_range(self):
        dates = _resolve_dates(None, None, "2026-04-10", "2026-04-15")
        assert len(dates) == 6
        assert dates[0] == datetime(2026, 4, 10, tzinfo=UTC)
        assert dates[-1] == datetime(2026, 4, 15, tzinfo=UTC)

    def test_range_requires_both(self):
        from click import UsageError

        with pytest.raises(UsageError, match="must be used together"):
            _resolve_dates(None, None, "2026-04-10", None)

    def test_range_start_after_end_raises(self):
        from click import UsageError

        with pytest.raises(UsageError, match="must be before"):
            _resolve_dates(None, None, "2026-04-20", "2026-04-10")

    def test_mutual_exclusion(self):
        from click import UsageError

        with pytest.raises(UsageError, match="mutually exclusive"):
            _resolve_dates("2026-04-15", "2026-04", None, None)


class TestMainCommand:
    @patch("fx_pulse.cli.get_store")
    @patch("fx_pulse.cli._resolve_scrapers")
    def test_dry_run_does_not_write(self, mock_resolve, mock_store):
        mock_scraper = MagicMock()
        mock_scraper.source_name = "VISA"
        mock_scraper.fetch_all.return_value = {
            "USD": {"rate": 31.577, "reverse": 0.031668},
        }
        mock_resolve.return_value = [mock_scraper]

        runner = CliRunner()
        result = runner.invoke(main, ["--source", "VISA", "--date", "2026-04-15", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "USD/TWD" in result.output
        mock_store.return_value.upsert_rates.assert_not_called()

    def test_invalid_source_exits_with_error(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--source", "AMEX"])
        assert result.exit_code != 0
        assert "Unknown source" in result.output

    def test_mutual_exclusion_exits_with_error(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--date", "2026-04-15", "--month", "2026-04"])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output


class TestJcbFetchMonth:
    def test_extracts_multiple_days(self):
        from tests.test_scraper_jcb import MOCK_TABLE_PAGE1, MOCK_TABLE_PAGE2

        scraper = JcbScraper()
        # Test _parse_pdf_multi logic via _extract_from_table
        result_day1 = scraper._extract_from_table(MOCK_TABLE_PAGE1, 1)
        result_day2 = scraper._extract_from_table(MOCK_TABLE_PAGE1, 2)
        result_day16 = scraper._extract_from_table(MOCK_TABLE_PAGE2, 16)

        assert result_day1 is not None
        assert result_day2 is not None
        assert result_day16 is not None
        assert result_day1["USD"]["rate"] == 31.968
        assert result_day2["USD"]["rate"] == 32.032
        assert result_day16["USD"]["rate"] == 31.617
