"""CLI entrypoint for FX Pulse scraper."""

from __future__ import annotations

import calendar
import json
import logging
import random
import sys
import time
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import click

from .config import settings
from .models.rate import CurrencyRate
from .scraper.base import BatchFetchError, CloudflareBlockedError
from .scraper.cooldown import Cooldowns
from .scraper.jcb import JcbScraper
from .scraper.mastercard import MastercardScraper
from .scraper.retry import PermanentHTTPError, RateLimitError
from .scraper.visa import VisaScraper
from .store import get_store

log = logging.getLogger(__name__)

SCRAPER_MAP: dict[str, type] = {
    "visa": VisaScraper,
    "mastercard": MastercardScraper,
    "jcb": JcbScraper,
}


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def _resolve_scrapers(source: str | None) -> list[Any]:
    """Build scraper instances from --source flag."""
    if source is None:
        return [VisaScraper(), MastercardScraper(), JcbScraper()]

    scrapers: list[Any] = []
    for name in source.split(","):
        key = name.strip().lower()
        if key not in SCRAPER_MAP:
            raise click.BadParameter(
                f"Unknown source '{name.strip()}'. Available: {', '.join(SCRAPER_MAP)}",
                param_hint="'--source'",
            )
        if not any(isinstance(scraper, SCRAPER_MAP[key]) for scraper in scrapers):
            scrapers.append(SCRAPER_MAP[key]())
    return scrapers


def _resolve_dates(
    target_date: str | None,
    target_month: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list[datetime]:
    """Parse date options into a list of datetime objects."""
    specified = sum(x is not None for x in [target_date, target_month, date_from or date_to])
    if specified > 1:
        raise click.UsageError("Options --date, --month, and --from/--to are mutually exclusive.")

    today = datetime.now(UTC)

    def parse_date(value: str, option: str) -> date:
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError
            if parsed > today.date():
                raise click.BadParameter("Date cannot be in the future", param_hint=option)
            return parsed
        except ValueError as exc:
            raise click.BadParameter("Expected a valid YYYY-MM-DD date", param_hint=option) from exc

    if target_date:
        d = parse_date(target_date, "--date")
        return [datetime(d.year, d.month, d.day, tzinfo=UTC)]

    if target_month:
        parts = target_month.split("-")
        if len(parts) != 2:
            raise click.BadParameter("Expected format YYYY-MM", param_hint="'--month'")
        try:
            year, month = int(parts[0]), int(parts[1])
            if f"{year:04d}-{month:02d}" != target_month:
                raise ValueError
            start = date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
        except ValueError as exc:
            raise click.BadParameter("Expected a valid YYYY-MM", param_hint="--month") from exc
        if start > today.date():
            raise click.BadParameter("Month cannot be in the future", param_hint="--month")
        end = date(year, month, last_day)
        # Don't go past today
        if end > today.date():
            end = today.date()
        start = date(year, month, 1)
        return [
            datetime(start.year, start.month, start.day, tzinfo=UTC) + timedelta(days=i)
            for i in range((end - start).days + 1)
        ]

    if date_from or date_to:
        if not date_from or not date_to:
            raise click.UsageError("--from and --to must be used together.")
        start = parse_date(date_from, "--from")
        end = parse_date(date_to, "--to")
        if start > end:
            raise click.UsageError("--from must be before --to.")
        return [
            datetime(start.year, start.month, start.day, tzinfo=UTC) + timedelta(days=i)
            for i in range((end - start).days + 1)
        ]

    return [today]


def _print_rates(date_key: str, source: str, rates: dict[str, CurrencyRate]) -> None:
    """Pretty-print rates for --dry-run mode."""
    click.echo(click.style(f"\n[{date_key}] {source}", fg="cyan", bold=True))
    for currency, r in sorted(rates.items()):
        rate_str = f"{r.rate:.10f}" if r.rate < 1 else f"{r.rate:.4f}"
        click.echo(f"  {currency}/TWD  rate={rate_str}  reverse={r.reverse:.6f}")


def _run_dates(
    scraper: Any,
    dates: list[datetime],
    *,
    dry_run: bool,
    store: Any,
    missing_only: bool = False,
) -> dict[str, Any]:
    """Save each date independently and preserve successful parts of a failed batch."""
    cooldowns = Cooldowns()
    active = cooldowns.active(scraper.source_name)
    eligible = any(scraper.source_name != "JCB" or d.weekday() < 5 for d in dates)
    if active and eligible:
        return {
            "status": "blocked",
            "currencies": 0,
            "currencies_saved": 0,
            "cooldown_active": True,
            "consecutive_blocks": active.consecutive_blocks,
            "next_retry_at": active.next_retry_at.isoformat(),
            "error": f"Cooling down until {active.next_retry_at.isoformat()}; no request made",
        }
    cooldown_entry = None
    currencies_fetched = 0
    currencies_saved = 0
    errors: list[str] = []
    blocked = False
    attempted = False
    skipped = 0
    for d in dates:
        date_key = d.strftime("%Y-%m-%d")
        if scraper.source_name == "JCB" and d.weekday() >= 5:
            skipped += 1
            continue
        raw: dict[str, dict[str, float]] = {}
        failure: Exception | None = None
        try:
            if missing_only:
                existing = (
                    store.export_payload().rates.get(date_key, {}).get(scraper.source_name, {})
                )
                currencies = [c for c in settings.currencies if c not in existing]
                if not currencies:
                    continue
            if attempted:
                time.sleep(random.uniform(settings.scraper_delay_min, settings.scraper_delay_max))
            attempted = True
            raw = (
                scraper.fetch_all(d, currencies=currencies)
                if missing_only
                else scraper.fetch_all(d)
            )
        except BatchFetchError as exc:
            raw, failure = exc.rates, exc.cause
        except Exception as exc:
            failure = exc

        try:
            if raw:
                rates = {c: CurrencyRate(**v) for c, v in raw.items()}
                if dry_run:
                    _print_rates(date_key, scraper.source_name, rates)
                else:
                    store.upsert_rates(date_key, scraper.source_name, rates)
                    currencies_saved += len(rates)
                currencies_fetched = max(currencies_fetched, len(rates))
            if failure is None:
                expected = currencies if missing_only else settings.currencies
                # All real scrapers should return the requested set, including JCB's parsed table.
                if set(expected) - raw.keys():
                    failure = ValueError("Source returned an incomplete currency set")
        except Exception as exc:
            errors.append(f"{date_key}: could not save rates: {exc}")
        if failure is not None:
            errors.append(f"{date_key}: {failure}")
            log.warning("%s: %s", scraper.source_name, errors[-1])
            if isinstance(failure, (CloudflareBlockedError, RateLimitError)):
                blocked = True
                if not dry_run:
                    cooldown_entry = cooldowns.block(
                        scraper.source_name, failure.retry_after_seconds
                    )
                break
            if isinstance(failure, PermanentHTTPError):
                break

    if attempted and not errors and not dry_run:
        cooldowns.success(scraper.source_name)
    if errors:
        status = "blocked" if blocked else "error"
    else:
        status = "ok" if attempted else "skipped"
    result: dict[str, Any] = {
        "status": status,
        "currencies": currencies_fetched,
        "currencies_saved": currencies_saved,
    }
    if errors:
        result.update(error="; ".join(errors), partial_success=currencies_fetched > 0)
    if cooldown_entry:
        result["consecutive_blocks"] = cooldown_entry.consecutive_blocks
        result["next_retry_at"] = cooldown_entry.next_retry_at.isoformat()
    if skipped:
        result["skipped_dates"] = skipped
        result["note"] = "JCB weekend dates are not requested; no previous-day rates substituted"
    return result


@click.command()
@click.option("--source", default=None, help="Comma-separated sources: VISA,Mastercard,JCB")
@click.option("--date", "target_date", default=None, help="Single date (YYYY-MM-DD)")
@click.option("--month", "target_month", default=None, help="Full month (YYYY-MM)")
@click.option("--from", "date_from", default=None, help="Range start (YYYY-MM-DD)")
@click.option("--to", "date_to", default=None, help="Range end (YYYY-MM-DD)")
@click.option("--dry-run", is_flag=True, help="Print results without writing to store")
@click.option(
    "--delay",
    default=None,
    type=click.FloatRange(min=0),
    help="Fixed delay between requests (seconds)",
)
@click.option("--result-file", default=None, help="Write scrape result summary to this JSON path")
def main(
    source: str | None,
    target_date: str | None,
    target_month: str | None,
    date_from: str | None,
    date_to: str | None,
    dry_run: bool,
    delay: float | None,
    result_file: str | None,
) -> None:
    """Fetch exchange rates from card network APIs."""
    _setup_logging()

    dates = _resolve_dates(target_date, target_month, date_from, date_to)
    scrapers = _resolve_scrapers(source)
    store = get_store()

    # Override delay if specified
    if delay is not None:
        settings.scraper_delay_min = delay
        settings.scraper_delay_max = delay

    log.info(
        "Fetching rates | dates=%d (%s ~ %s) | sources=%s | dry_run=%s",
        len(dates),
        dates[0].strftime("%Y-%m-%d"),
        dates[-1].strftime("%Y-%m-%d"),
        [s.source_name for s in scrapers],
        dry_run,
    )

    scraper_results: dict[str, dict[str, Any]] = {}

    for scraper in scrapers:
        scraper_results[scraper.source_name] = _run_dates(
            scraper, dates, dry_run=dry_run, store=store
        )

    if result_file:
        statuses = {r["status"] for r in scraper_results.values()}
        if statuses <= {"ok", "skipped"}:
            overall = "ok"
        elif "blocked" in statuses and not statuses & {"error"}:
            overall = "blocked"
        else:
            overall = "error"
        payload = {
            "date": dates[-1].strftime("%Y-%m-%d"),
            "status": overall,
            "results": scraper_results,
            "window": {"from": dates[0].date().isoformat(), "to": dates[-1].date().isoformat()},
            "sources": [scraper.source_name for scraper in scrapers],
        }
        result_path = Path(result_file)
        try:
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(json.dumps(payload, indent=2))
        except OSError:
            log.exception(
                "Failed to write result summary file to %s; scraping completed",
                result_path,
            )


@click.command()
@click.option(
    "--days",
    default=7,
    type=click.IntRange(min=1),
    show_default=True,
    help="Look-back window in days",
)
@click.option("--source", default=None, help="Comma-separated sources to check (default: all)")
@click.option("--dry-run", is_flag=True, help="Print missing pairs without scraping")
@click.option("--result-file", default=None, help="Write backfill result summary to this JSON path")
def backfill(
    days: int,
    source: str | None,
    dry_run: bool,
    result_file: str | None,
) -> None:
    """Detect and fill missing (date, source) pairs from the last N days."""
    _setup_logging()

    scrapers = _resolve_scrapers(source)
    # Deduplicate while preserving order (guards against --source visa,VISA)
    seen: set[str] = set()
    source_names: list[str] = []
    for s in scrapers:
        if s.source_name not in seen:
            seen.add(s.source_name)
            source_names.append(s.source_name)
    store = get_store()

    report_end = datetime.now(UTC).date()
    report_context = {
        "date": report_end.isoformat(),
        "window": {
            "from": (report_end - timedelta(days=days - 1)).isoformat(),
            "to": report_end.isoformat(),
        },
        "sources": source_names,
        "mode": "backfill",
    }
    missing = store.find_missing(source_names, days=days)

    def missing_currency_count(pairs: list[tuple[str, str]]) -> int:
        payload = store.export_payload()
        return sum(
            len(set(settings.currencies) - payload.rates.get(day, {}).get(src, {}).keys())
            for day, src in pairs
        )

    currencies_missing_before = missing_currency_count(missing)

    if not missing:
        log.info("Backfill: nothing missing in the last %d days.", days)
        if result_file:
            result_path = Path(result_file)
            try:
                result_path.parent.mkdir(parents=True, exist_ok=True)
                result_path.write_text(
                    json.dumps(
                        {
                            **report_context,
                            "results": {},
                            "status": "ok",
                            "missing_found": 0,
                            "missing_remaining": 0,
                            "currencies_recovered": 0,
                            "currencies_remaining": 0,
                        }
                    )
                )
            except OSError:
                log.exception("Failed to write result summary file to %s", result_path)
        return

    log.info("Backfill: %d missing (date, source) pairs found", len(missing))
    log.debug("Backfill: missing pairs — %s", missing)

    if dry_run:
        for date_key, src in missing:
            click.echo(f"  MISSING  {date_key}  {src}")
        if result_file:
            result_path = Path(result_file)
            try:
                result_path.parent.mkdir(parents=True, exist_ok=True)
                result_path.write_text(
                    json.dumps(
                        {
                            **report_context,
                            "status": "dry_run",
                            "dry_run": True,
                            "missing_found": len(missing),
                            "results": {},
                        }
                    )
                )
            except OSError:
                log.exception("Failed to write result summary file to %s", result_path)
        return

    # Group missing pairs by source so we can reuse the JCB batch optimisation
    by_source: dict[str, list[str]] = defaultdict(list)
    for date_key, src in missing:
        by_source[src].append(date_key)

    scraper_map = {s.source_name: s for s in scrapers}
    scraper_results: dict[str, dict[str, Any]] = {}

    for src, date_keys in by_source.items():
        scraper = scraper_map[src]
        sorted_date_keys = sorted(date_keys)
        dates_dt = [datetime.fromisoformat(dk).replace(tzinfo=UTC) for dk in sorted_date_keys]

        log.info("Backfill: scraping %s for %d date(s): %s", src, len(dates_dt), sorted_date_keys)

        scraper_results[src] = _run_dates(
            scraper, dates_dt, dry_run=False, store=store, missing_only=True
        )

    if result_file:
        statuses = {r["status"] for r in scraper_results.values()}
        if statuses <= {"ok", "skipped"}:
            overall = "ok"
        elif "blocked" in statuses and "error" not in statuses:
            overall = "blocked"
        else:
            overall = "error"
        result_path = Path(result_file)
        try:
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(
                json.dumps(
                    {
                        **report_context,
                        "status": overall,
                        "missing_found": len(missing),
                        "missing_remaining": len(store.find_missing(source_names, days=days)),
                        "currencies_recovered": currencies_missing_before
                        - missing_currency_count(missing),
                        "currencies_remaining": missing_currency_count(missing),
                        "results": scraper_results,
                    },
                    indent=2,
                )
            )
        except OSError:
            log.exception(
                "Failed to write result summary file to %s; backfill completed", result_path
            )
