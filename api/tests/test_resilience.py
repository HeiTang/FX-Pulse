"""Regression coverage for partial batches, recovery, and bounded HTTP retries."""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import MagicMock, patch

import pytest

from fx_pulse.cli import _run_dates
from fx_pulse.config import Settings, settings
from fx_pulse.models.rate import CurrencyRate
from fx_pulse.scraper.base import BatchFetchError, CloudflareBlockedError
from fx_pulse.scraper.cooldown import Cooldowns
from fx_pulse.scraper.jcb import JcbScraper
from fx_pulse.scraper.retry import PermanentHTTPError, RateLimitError, retry_delay
from fx_pulse.scraper.visa import VisaScraper
from fx_pulse.store.json_store import JsonStore

USD = {"rate": 32.0, "reverse": 0.03125}
JPY = {"rate": 0.2, "reverse": 5.0}
DAY = datetime(2026, 10, 3, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    monkeypatch.setattr(settings, "currencies", ["USD", "JPY"])


def response(status, headers=None, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.text = text
    if status >= 400:
        resp.raise_for_status.side_effect = RuntimeError(f"HTTP {status}")
    return resp


def test_partial_block_saves_usd_and_missing_only_recovers_jpy(tmp_path):
    store = JsonStore(tmp_path / "rates.json")
    scraper = VisaScraper()
    with patch.object(scraper, "fetch_one", side_effect=[USD, CloudflareBlockedError("403")]):
        report = _run_dates(scraper, [DAY, DAY + timedelta(days=1)], dry_run=False, store=store)
    assert report["status"] == "blocked"
    assert report["partial_success"] is True
    assert store.export_payload().rates["2026-10-03"]["VISA"]["USD"].rate == 32
    with patch("fx_pulse.store.base.datetime") as dt:
        dt.now.return_value.date.return_value = DAY.date()
        assert store.find_missing(["VISA"], days=1) == [("2026-10-03", "VISA")]
    with patch.object(scraper, "fetch_all") as fetch:
        deferred = _run_dates(scraper, [DAY], dry_run=False, store=store, missing_only=True)
    assert deferred["cooldown_active"] is True
    fetch.assert_not_called()
    cooldowns = Cooldowns()
    cooldowns.state.sources["VISA"].next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
    cooldowns._save()
    with patch.object(scraper, "fetch_all", return_value={"JPY": JPY}) as fetch:
        report = _run_dates(scraper, [DAY], dry_run=False, store=store, missing_only=True)
    fetch.assert_called_once_with(DAY, currencies=["JPY"])
    assert report["status"] == "ok"
    assert set(store.export_payload().rates["2026-10-03"]["VISA"]) == {"USD", "JPY"}
    with patch("fx_pulse.store.base.datetime") as dt:
        dt.now.return_value.date.return_value = DAY.date()
        assert store.find_missing(["VISA"], days=1) == []
    with patch.object(scraper, "fetch_all") as fetch:
        _run_dates(scraper, [DAY], dry_run=False, store=store, missing_only=True)
    fetch.assert_not_called()


def test_failed_batch_dry_run_preserves_file(tmp_path):
    path = tmp_path / "rates.json"
    store = JsonStore(path)
    store.upsert_rates("2026-10-03", "VISA", {"JPY": CurrencyRate(**JPY)})
    before = path.read_bytes()
    scraper = VisaScraper()
    with patch.object(scraper, "fetch_one", side_effect=[USD, RuntimeError("timeout")]):
        report = _run_dates(scraper, [DAY], dry_run=True, store=store)
    assert report["status"] == "error"
    assert path.read_bytes() == before


def test_jcb_weekend_is_skipped_without_request_or_fabricated_data(tmp_path):
    store = JsonStore(tmp_path / "rates.json")
    scraper = JcbScraper()
    with patch.object(scraper, "fetch_all") as fetch:
        report = _run_dates(scraper, [DAY], dry_run=False, store=store)
    assert report["status"] == "skipped"
    fetch.assert_not_called()
    assert store.export_payload().rates == {}


def test_jcb_incomplete_response_is_saved_and_reported(tmp_path):
    store = JsonStore(tmp_path / "rates.json")
    scraper = JcbScraper()
    with patch.object(scraper, "fetch_all", return_value={"USD": USD}):
        report = _run_dates(scraper, [DAY - timedelta(days=1)], dry_run=False, store=store)
    assert report["status"] == "error"
    assert report["partial_success"] is True


@pytest.mark.parametrize("attempt,ceiling", [(0, 5), (1, 10), (4, 60), (8, 60)])
def test_exponential_full_jitter_and_cap(attempt, ceiling):
    with patch("fx_pulse.scraper.retry.random.uniform", return_value=2) as jitter:
        assert retry_delay(attempt) == 2
    jitter.assert_called_once_with(0, ceiling)


@pytest.mark.parametrize("date_header", [False, True])
def test_retry_after_is_a_floor(date_header):
    header = format_datetime(datetime.now(UTC) + timedelta(seconds=25)) if date_header else "20"
    with patch("fx_pulse.scraper.retry.random.uniform", return_value=1):
        assert 19 <= retry_delay(0, response(429, {"retry-after": header})) <= 26


def test_long_retry_after_stops_instead_of_retrying_early():
    with pytest.raises(RateLimitError):
        retry_delay(0, response(429, {"retry-after": "3600"}))


@pytest.mark.parametrize("header", ["bad", "nan", "inf", "-10"])
def test_invalid_retry_after_has_safe_fallback(header):
    with patch("fx_pulse.scraper.retry.random.uniform", return_value=2):
        assert retry_delay(0, response(429, {"retry-after": header})) == 2


@pytest.mark.parametrize("kind", [VisaScraper, JcbScraper])
@pytest.mark.parametrize("status", [403, 404])
def test_permanent_http_errors_do_not_retry(kind, status):
    scraper = kind()
    session = MagicMock()
    session.get.return_value = response(status)
    scraper._session = session
    with pytest.raises((PermanentHTTPError, ValueError)):
        if kind is VisaScraper:
            scraper.fetch_one("USD", "10/03/2026")
        else:
            scraper._fetch_raw_rates(DAY)
    assert session.get.call_count == 1


@pytest.mark.parametrize("kind", [VisaScraper, JcbScraper])
def test_cloudflare_challenge_stops_immediately(kind):
    scraper = kind()
    session = MagicMock()
    session.get.return_value = response(403, {"cf-mitigated": "challenge"})
    scraper._session = session
    with pytest.raises(CloudflareBlockedError):
        if kind is VisaScraper:
            scraper.fetch_one("USD", "10/03/2026")
        else:
            scraper._fetch_raw_rates(DAY)
    assert session.get.call_count == 1


@pytest.mark.parametrize("status", [429, 503])
def test_cf_ray_on_ordinary_error_still_allows_bounded_retry(status):
    scraper = VisaScraper()
    session = MagicMock()
    session.get.return_value = response(status, {"cf-ray": "test", "retry-after": "12"})
    with patch("fx_pulse.scraper.base.cf_requests.Session", return_value=session):
        with pytest.raises(RuntimeError):
            scraper.fetch_one("USD", "10/03/2026")
    assert session.get.call_count == settings.scraper_max_retries


def test_retry_after_wait_is_applied_before_next_request():
    scraper = VisaScraper()
    session = MagicMock()
    session.get.side_effect = [response(429, {"retry-after": "20"}), response(200)]
    with (
        patch("fx_pulse.scraper.base.cf_requests.Session", return_value=session),
        patch.object(scraper, "_parse_response", return_value=USD),
        patch("fx_pulse.scraper.base.time.sleep") as sleep,
    ):
        assert scraper.fetch_one("USD", "10/03/2026") == USD
    sleep.assert_called_once()
    assert sleep.call_args.args[0] >= 20


@pytest.mark.parametrize("kind", [VisaScraper, JcbScraper])
def test_session_keeps_impersonation_user_agent(kind):
    session = MagicMock()
    with patch("fx_pulse.scraper.base.cf_requests.Session", return_value=session):
        assert kind().session is session
    assert "user-agent" not in session.headers.update.call_args.args[0]


@pytest.mark.parametrize(
    "values",
    [
        {"scraper_delay_min": 6, "scraper_delay_max": 3},
        {"scraper_max_retries": 0},
        {"scraper_backoff_base": 0},
        {"scraper_backoff_cap": float("nan")},
    ],
)
def test_invalid_retry_configuration_is_rejected(values):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)


def test_batch_error_preserves_original_failure_and_successes():
    scraper = VisaScraper()
    cause = RateLimitError("wait")
    with patch.object(scraper, "fetch_one", side_effect=[USD, cause]):
        with pytest.raises(BatchFetchError) as error:
            scraper.fetch_all(DAY)
    assert error.value.cause is cause
    assert error.value.rates == {"USD": USD}


def test_malformed_success_response_is_not_retried():
    scraper = VisaScraper()
    session = MagicMock()
    resp = response(200)
    resp.json.return_value = {"status": "success"}
    session.get.return_value = resp
    scraper._session = session
    with pytest.raises(KeyError):
        scraper.fetch_one("USD", "10/03/2026")
    assert session.get.call_count == 1


def test_jcb_later_failure_preserves_earlier_date(tmp_path):
    store = JsonStore(tmp_path / "rates.json")
    scraper = JcbScraper()
    dates = [datetime(2026, 10, day, tzinfo=UTC) for day in (1, 2)]
    with patch.object(
        scraper, "fetch_all", side_effect=[{"USD": USD, "JPY": JPY}, ValueError("bad table")]
    ):
        report = _run_dates(scraper, dates, dry_run=False, store=store)
    assert report["status"] == "error"
    assert report["partial_success"] is True
    assert set(store.export_payload().rates) == {"2026-10-01"}


def test_source_stops_after_long_retry_after(tmp_path):
    store = JsonStore(tmp_path / "rates.json")
    scraper = VisaScraper()
    session = MagicMock()
    session.get.return_value = response(429, {"retry-after": "3600"})
    scraper._session = session
    report = _run_dates(scraper, [DAY, DAY + timedelta(days=1)], dry_run=False, store=store)
    assert report["status"] == "blocked"
    assert session.get.call_count == 1
    assert not store.export_payload().rates
