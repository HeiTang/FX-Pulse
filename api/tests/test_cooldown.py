"""Persistent cooldowns survive runs without suppressing other sources."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from fx_pulse.cli import _run_dates, backfill
from fx_pulse.config import settings
from fx_pulse.models.rate import CurrencyRate
from fx_pulse.scraper.base import CloudflareBlockedError
from fx_pulse.scraper.cooldown import Cooldowns
from fx_pulse.scraper.retry import RateLimitError, retry_delay
from fx_pulse.scraper.visa import VisaScraper
from fx_pulse.store.json_store import JsonStore

NOW = datetime(2026, 10, 3, tzinfo=UTC)
RATE = {"rate": 32, "reverse": 1 / 32}


def test_persist_reload_and_escalate_with_cap():
    now = NOW
    for hours in (6, 12, 24, 24):
        state = Cooldowns()
        entry = state.block("VISA", now=now)
        assert entry.next_retry_at == now + timedelta(hours=hours)
        reloaded = Cooldowns()
        assert reloaded.active("VISA", now=now) == entry
        assert reloaded.active("Mastercard", now=now) is None
        assert reloaded.active("VISA", now=entry.next_retry_at) is None
        now = entry.next_retry_at
    Cooldowns().success("VISA")
    assert not Cooldowns().state.sources
    assert Cooldowns().block("VISA", now=now).consecutive_blocks == 1


def test_server_deadline_longer_than_24_hours_is_preserved():
    entry = Cooldowns().block("VISA", retry_after_seconds=172800, now=NOW)
    assert entry.next_retry_at == NOW + timedelta(days=2)
    assert Cooldowns().active("VISA", now=NOW + timedelta(hours=25))


def test_retry_after_survives_exception_to_disk():
    class Response:
        headers = {"retry-after": "172800"}

    with pytest.raises(RateLimitError) as error:
        retry_delay(0, Response())
    entry = Cooldowns().block("VISA", error.value.retry_after_seconds, now=NOW)
    assert Cooldowns().active("VISA", now=NOW).next_retry_at == entry.next_retry_at


def test_cooling_run_does_not_request_or_extend_deadline(tmp_path):
    state = Cooldowns()
    entry = state.block("VISA")
    before = settings.scraper_state_file.read_bytes()
    scraper = VisaScraper()
    with patch.object(scraper, "fetch_all") as fetch:
        report = _run_dates(scraper, [NOW], dry_run=False, store=JsonStore(tmp_path / "rates.json"))
    fetch.assert_not_called()
    assert report["next_retry_at"] == entry.next_retry_at.isoformat()
    assert report["cooldown_active"] is True
    assert settings.scraper_state_file.read_bytes() == before


def test_success_clears_only_its_source_after_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "currencies", ["USD"])
    state = Cooldowns()
    state.block("VISA", now=NOW - timedelta(days=2))
    state.block("Mastercard")
    scraper = VisaScraper()
    with patch.object(scraper, "fetch_all", return_value={"USD": RATE}):
        report = _run_dates(scraper, [NOW], dry_run=False, store=JsonStore(tmp_path / "rates.json"))
    assert report["status"] == "ok"
    assert set(Cooldowns().state.sources) == {"Mastercard"}


def test_dry_run_does_not_write_cooldown(tmp_path):
    scraper = VisaScraper()
    with patch.object(scraper, "fetch_all", side_effect=CloudflareBlockedError("403")):
        _run_dates(scraper, [NOW], dry_run=True, store=JsonStore(tmp_path / "rates.json"))
    assert not settings.scraper_state_file.exists()


def test_corrupt_state_is_not_ignored():
    settings.scraper_state_file.write_text('{"sources": {"VISA": {}}}')
    with pytest.raises(ValueError):
        Cooldowns()


def test_failed_atomic_save_keeps_old_state():
    Cooldowns().block("VISA", now=NOW)
    before = settings.scraper_state_file.read_bytes()
    with patch.object(Path, "replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            Cooldowns().block("VISA", now=NOW + timedelta(hours=6))
    assert settings.scraper_state_file.read_bytes() == before


def test_backfill_reports_recovered_and_remaining_currencies(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "currencies", ["USD", "JPY"])
    store = JsonStore(tmp_path / "rates.json")
    today = datetime.now(UTC).date().isoformat()
    store.upsert_rates(today, "VISA", {"USD": CurrencyRate(**RATE)})
    report_path = tmp_path / "report.json"
    with (
        patch("fx_pulse.cli.get_store", return_value=store),
        patch.object(VisaScraper, "fetch_all", return_value={"JPY": {"rate": 0.2, "reverse": 5}}),
    ):
        result = CliRunner().invoke(
            backfill, ["--source", "VISA", "--days", "1", "--result-file", str(report_path)]
        )
    assert result.exit_code == 0, result.output
    report = json.loads(report_path.read_text())
    assert report["missing_found"] == 1
    assert report["missing_remaining"] == 0
    assert report["currencies_recovered"] == 1
    assert report["currencies_remaining"] == 0


def test_backfill_reports_cooling_source_as_still_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "currencies", ["USD", "JPY"])
    Cooldowns().block("VISA")
    report_path = tmp_path / "report.json"
    with (
        patch("fx_pulse.cli.get_store", return_value=JsonStore(tmp_path / "rates.json")),
        patch.object(VisaScraper, "fetch_all") as fetch,
    ):
        result = CliRunner().invoke(
            backfill, ["--source", "VISA", "--days", "1", "--result-file", str(report_path)]
        )
    assert result.exit_code == 0, result.output
    fetch.assert_not_called()
    report = json.loads(report_path.read_text())
    assert report["currencies_recovered"] == 0
    assert report["currencies_remaining"] == 2
    assert report["results"]["VISA"]["cooldown_active"] is True


def test_two_separate_cli_processes_honor_saved_cooldown(tmp_path):
    Cooldowns().block("VISA")
    before = settings.scraper_state_file.read_bytes()
    report_path = tmp_path / "report.json"
    env = {
        **os.environ,
        "FX_SCRAPER_STATE_FILE": str(settings.scraper_state_file),
        "FX_DATA_FILE": str(tmp_path / "rates.json"),
    }
    code = """
import sys
from unittest.mock import patch
from fx_pulse.cli import main
from fx_pulse.scraper.visa import VisaScraper
with patch.object(VisaScraper, 'fetch_all', side_effect=AssertionError('Unexpected HTTP request')):
    main(['--source', 'VISA', '--date', '2026-10-03', '--result-file', sys.argv[1]])
"""
    for _ in range(2):
        run = subprocess.run(
            [sys.executable, "-c", code, str(report_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert run.returncode == 0, run.stderr
        assert json.loads(report_path.read_text())["results"]["VISA"]["cooldown_active"] is True
        assert settings.scraper_state_file.read_bytes() == before


def test_dry_run_success_does_not_reset_persistent_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "currencies", ["USD"])
    Cooldowns().block("VISA", now=datetime.now(UTC) - timedelta(days=2))
    before = settings.scraper_state_file.read_bytes()
    scraper = VisaScraper()
    with patch.object(scraper, "fetch_all", return_value={"USD": RATE}):
        _run_dates(scraper, [NOW], dry_run=True, store=JsonStore(tmp_path / "rates.json"))
    assert settings.scraper_state_file.read_bytes() == before
