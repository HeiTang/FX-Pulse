"""CLI entrypoint for FX Pulse scraper."""

from __future__ import annotations

import calendar
import json
import logging
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import click

from .models.rate import CurrencyRate
from .scraper.base import CloudflareBlockedError
from .scraper.jcb import JcbScraper
from .scraper.mastercard import MastercardScraper
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

    if target_date:
        d = date.fromisoformat(target_date)
        return [datetime(d.year, d.month, d.day, tzinfo=UTC)]

    if target_month:
        parts = target_month.split("-")
        if len(parts) != 2:
            raise click.BadParameter("Expected format YYYY-MM", param_hint="'--month'")
        year, month = int(parts[0]), int(parts[1])
        last_day = calendar.monthrange(year, month)[1]
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
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
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


def _run_jcb_batch(
    scraper: JcbScraper,
    dates: list[datetime],
    *,
    dry_run: bool,
    store: Any,
) -> dict[str, Any]:
    """Run JCB scraper with month-level batch optimization.

    Returns a scraper result dict compatible with the --result-file format.
    """
    by_month: dict[tuple[int, int], list[int]] = defaultdict(list)
    for d in dates:
        by_month[(d.year, d.month)].append(d.day)

    currencies_fetched = 0
    last_error: str | None = None

    for (year, month), days in sorted(by_month.items()):
        try:
            month_rates = scraper.fetch_month(year, month, days)
            for day, raw in month_rates.items():
                date_key = f"{year:04d}-{month:02d}-{day:02d}"
                rates = {c: CurrencyRate(**v) for c, v in raw.items()}
                currencies_fetched = max(currencies_fetched, len(raw))
                if dry_run:
                    _print_rates(date_key, scraper.source_name, rates)
                else:
                    store.upsert_rates(date_key, scraper.source_name, rates)
        except CloudflareBlockedError as exc:
            return {
                "status": "blocked",
                "currencies": currencies_fetched,
                "error": str(exc),
            }
        except Exception as exc:
            last_error = str(exc)
            log.exception(
                "Scraper %s failed for %04d-%02d",
                scraper.source_name,
                year,
                month,
            )

    if last_error:
        return {
            "status": "error",
            "currencies": currencies_fetched,
            "error": last_error,
            "partial_success": currencies_fetched > 0,
        }
    return {"status": "ok", "currencies": currencies_fetched}


@click.command()
@click.option("--source", default=None, help="Comma-separated sources: VISA,Mastercard,JCB")
@click.option("--date", "target_date", default=None, help="Single date (YYYY-MM-DD)")
@click.option("--month", "target_month", default=None, help="Full month (YYYY-MM)")
@click.option("--from", "date_from", default=None, help="Range start (YYYY-MM-DD)")
@click.option("--to", "date_to", default=None, help="Range end (YYYY-MM-DD)")
@click.option("--dry-run", is_flag=True, help="Print results without writing to store")
@click.option("--delay", default=None, type=float, help="Fixed delay between requests (seconds)")
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
    multi_day = len(dates) > 1

    # Override delay if specified
    if delay is not None:
        from .config import settings

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
        # JCB optimization: batch by month when fetching multiple days
        if isinstance(scraper, JcbScraper) and multi_day:
            scraper_results[scraper.source_name] = _run_jcb_batch(
                scraper, dates, dry_run=dry_run, store=store
            )
            continue

        currencies_fetched = 0
        last_error: str | None = None
        cf_blocked = False

        for d in dates:
            date_key = d.strftime("%Y-%m-%d")
            try:
                raw = scraper.fetch_all(d)
                rates = {c: CurrencyRate(**v) for c, v in raw.items()}
                currencies_fetched = max(currencies_fetched, len(raw))
                if dry_run:
                    _print_rates(date_key, scraper.source_name, rates)
                else:
                    store.upsert_rates(date_key, scraper.source_name, rates)
            except CloudflareBlockedError as exc:
                cf_blocked = True
                last_error = str(exc)
                log.error(
                    "Scraper %s blocked by Cloudflare for %s",
                    scraper.source_name,
                    date_key,
                )
                break  # no point retrying other dates if CF is blocking
            except Exception as exc:
                last_error = str(exc)
                log.exception(
                    "Scraper %s failed for %s — continuing",
                    scraper.source_name,
                    date_key,
                )

        if cf_blocked:
            scraper_results[scraper.source_name] = {
                "status": "blocked",
                "currencies": currencies_fetched,
                "error": last_error,
            }
        elif last_error:
            scraper_results[scraper.source_name] = {
                "status": "error",
                "currencies": currencies_fetched,
                "error": last_error,
                "partial_success": currencies_fetched > 0,
            }
        else:
            scraper_results[scraper.source_name] = {
                "status": "ok",
                "currencies": currencies_fetched,
            }

    if result_file:
        statuses = {r["status"] for r in scraper_results.values()}
        if statuses == {"ok"}:
            overall = "ok"
        elif "blocked" in statuses and not statuses & {"error"}:
            overall = "blocked"
        else:
            overall = "error"
        payload = {
            "date": dates[-1].strftime("%Y-%m-%d"),
            "status": overall,
            "results": scraper_results,
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

    missing = store.find_missing(source_names, days=days)

    if not missing:
        log.info("Backfill: nothing missing in the last %d days.", days)
        if result_file:
            result_path = Path(result_file)
            try:
                result_path.parent.mkdir(parents=True, exist_ok=True)
                result_path.write_text(json.dumps({"status": "ok", "missing_found": 0}))
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

        if isinstance(scraper, JcbScraper) and len(dates_dt) > 1:
            scraper_results[src] = _run_jcb_batch(scraper, dates_dt, dry_run=False, store=store)
        else:
            currencies_fetched = 0
            last_error: str | None = None
            cf_blocked = False

            for d in dates_dt:
                date_key = d.strftime("%Y-%m-%d")
                try:
                    raw = scraper.fetch_all(d)
                    rates = {c: CurrencyRate(**v) for c, v in raw.items()}
                    currencies_fetched = max(currencies_fetched, len(raw))
                    store.upsert_rates(date_key, scraper.source_name, rates)
                except CloudflareBlockedError as exc:
                    cf_blocked = True
                    last_error = str(exc)
                    log.error("Backfill: %s blocked by Cloudflare for %s", src, date_key)
                    break
                except Exception as exc:
                    last_error = str(exc)
                    log.exception("Backfill: %s failed for %s — continuing", src, date_key)

            if cf_blocked:
                scraper_results[src] = {
                    "status": "blocked",
                    "currencies": currencies_fetched,
                    "error": last_error,
                }
            elif last_error:
                scraper_results[src] = {
                    "status": "error",
                    "currencies": currencies_fetched,
                    "error": last_error,
                    "partial_success": currencies_fetched > 0,
                }
            else:
                scraper_results[src] = {"status": "ok", "currencies": currencies_fetched}

    if result_file:
        statuses = {r["status"] for r in scraper_results.values()}
        if statuses <= {"ok"}:
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
                    {"status": overall, "missing_found": len(missing), "results": scraper_results},
                    indent=2,
                )
            )
        except OSError:
            log.exception(
                "Failed to write result summary file to %s; backfill completed", result_path
            )
