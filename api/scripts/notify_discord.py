"""Send Discord notifications for FX Pulse scrape results.

Usage:
    # Daily rates summary → #fx-daily
    poetry run python scripts/notify_discord.py \
        --mode daily \
        --webhook "$DISCORD_WEBHOOK_FX_DAILY" \
        --result-file scrape_result.json

    # Alert on failure → #fx-alerts
    poetry run python scripts/notify_discord.py \
        --mode alert \
        --webhook "$DISCORD_WEBHOOK_FX_ALERTS" \
        --result-file scrape_result.json \
        --role-id "$DISCORD_ROLE_ID_ALERT"
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

RATES_JSON = Path(__file__).parent.parent.parent / "web" / "src" / "data" / "rates.json"

CURRENCIES = ["USD", "JPY", "EUR", "GBP", "HKD", "AUD", "KRW", "SGD"]

CURRENCY_LABEL = {
    "USD": "🇺🇸 USD",
    "JPY": "🇯🇵 JPY",
    "EUR": "🇪🇺 EUR",
    "GBP": "🇬🇧 GBP",
    "HKD": "🇭🇰 HKD",
    "AUD": "🇦🇺 AUD",
    "KRW": "🇰🇷 KRW",
    "SGD": "🇸🇬 SGD",
}

SOURCES = ["VISA", "Mastercard", "JCB"]

COLOR_GREEN = 0x57F287
COLOR_YELLOW = 0xFEE75C
COLOR_RED = 0xED4245


# ── Helpers ───────────────────────────────────────────────────────────────────


def _fmt_rate(rate: float) -> str:
    return f"{rate:.6f}" if rate < 1 else f"{rate:.4f}"


def _send(webhook_url: str, payload: dict) -> None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        webhook_url.strip(),
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "FXPulse-Bot/1.0 (https://github.com/0range/FX-Pulse)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Discord webhook returned {resp.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"Discord webhook HTTP error: {exc.code} — {body}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Discord webhook connection error: {exc.reason}") from None


# ── Embed builders ────────────────────────────────────────────────────────────


def _build_daily_payload(
    date_key: str,
    day_rates: dict,
    results: dict,
) -> dict:
    """Build the daily rates embed for #fx-daily."""
    fields = []

    for currency in CURRENCIES:
        vals: dict[str, float] = {}
        for src in SOURCES:
            r = day_rates.get(src, {}).get(currency)
            if r:
                vals[src] = r["rate"]

        if not vals:
            continue

        best_src = min(vals, key=lambda s: vals[s])
        worst_src = max(vals, key=lambda s: vals[s]) if len(vals) > 1 else None

        lines = []
        for src in SOURCES:
            if src not in vals:
                lines.append(f"`{src:<12}` —")
                continue
            rate_str = _fmt_rate(vals[src])
            if src == best_src:
                marker = " ⭐"
            elif src == worst_src:
                marker = " 🔴"
            else:
                marker = ""
            lines.append(f"`{src:<12}` {rate_str}{marker}")

        fields.append({
            "name": CURRENCY_LABEL[currency],
            "value": "\n".join(lines),
            "inline": True,
        })

    failed = [s for s, r in results.items() if r["status"] == "error"]
    color = COLOR_GREEN if not failed else COLOR_YELLOW

    status_parts = []
    for src, res in results.items():
        if res["status"] == "ok":
            status_parts.append(f"✅ {src}")
        else:
            status_parts.append(f"❌ {src}")

    return {
        "embeds": [
            {
                "title": f"📊 FX Pulse 每日匯率 · {date_key}",
                "color": color,
                "fields": fields,
                "footer": {"text": "  ·  ".join(status_parts)},
            }
        ]
    }


def _build_alert_payload(
    date_key: str,
    results: dict,
    role_id: str | None,
) -> dict:
    """Build the failure alert embed for #fx-alerts."""
    lines = []
    has_blocked = False
    for src, res in results.items():
        status = res["status"]
        if status == "ok":
            lines.append(f"✅ **{src}** — {res['currencies']} 幣別正常")
        elif status == "blocked":
            has_blocked = True
            error = res.get("error", "unknown")
            sanitized = error.replace("@", "＠")
            lines.append(f"🛡️ **{src}** — Cloudflare 阻擋 · {sanitized}")
        else:
            error = res.get("error", "unknown error")
            sanitized = error.replace("@", "＠")
            lines.append(f"❌ **{src}** — {sanitized}")

    all_blocked = all(r["status"] in ("ok", "blocked") for r in results.values())
    color = COLOR_YELLOW if all_blocked else COLOR_RED
    title = (
        f"🛡️ FX Pulse 遭 Cloudflare 阻擋 · {date_key}"
        if all_blocked and has_blocked
        else f"🚨 FX Pulse 爬蟲失敗 · {date_key}"
    )

    content = f"<@&{role_id}>" if role_id else ""

    allowed_mentions: dict = {"parse": []}
    if role_id:
        allowed_mentions = {"roles": [role_id]}

    return {
        "content": content,
        "allowed_mentions": allowed_mentions,
        "embeds": [
            {
                "title": title,
                "description": "\n".join(lines),
                "color": color,
            }
        ],
    }


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Send FX Pulse Discord notifications")
    parser.add_argument("--mode", choices=["daily", "alert"], required=True)
    parser.add_argument("--webhook", required=True, help="Discord webhook URL")
    parser.add_argument("--result-file", required=True, help="Path to scrape_result.json")
    parser.add_argument("--role-id", default=None, help="Discord role ID to @mention (alert only)")
    args = parser.parse_args()

    with open(args.result_file) as f:
        result = json.load(f)

    date_key: str = result["date"]
    results: dict = result["results"]

    if args.mode == "daily":
        with open(RATES_JSON) as f:
            rates_data = json.load(f)["rates"]
        day_rates = rates_data.get(date_key, {})
        payload = _build_daily_payload(date_key, day_rates, results)
    else:
        payload = _build_alert_payload(date_key, results, args.role_id)

    _send(args.webhook, payload)
    print(f"[notify_discord] Sent {args.mode} notification for {date_key}")


if __name__ == "__main__":
    main()
