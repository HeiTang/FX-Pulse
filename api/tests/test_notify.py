"""Notification payload tests; never send a webhook."""

from __future__ import annotations

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "notify_discord", Path(__file__).parents[1] / "scripts" / "notify_discord.py"
)
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)


def test_blocked_daily_source_uses_warning_color():
    payload = notify._build_daily_payload("2026-04-01", {}, {"VISA": {"status": "blocked"}})
    assert payload["embeds"][0]["color"] == notify.COLOR_YELLOW
    assert "交叉匯率估算" in payload["embeds"][0]["description"]


def test_alert_sanitizes_mentions_in_upstream_error():
    payload = notify._build_alert_payload(
        "2026-04-01", {"VISA": {"status": "error", "error": "@everyone failed"}}, None
    )
    assert "@everyone" not in payload["embeds"][0]["description"]
    assert payload["allowed_mentions"] == {"parse": []}
