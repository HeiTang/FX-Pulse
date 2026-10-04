"""Read-only GitHub Actions summary; does not scrape, save rates, or send notifications."""

from __future__ import annotations

import argparse
import html
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from fx_pulse.config import settings
from fx_pulse.models.rate import RatesPayload

SOURCES = ("VISA", "Mastercard", "JCB")
STATUSES = {"ok": "完成", "error": "失敗", "blocked": "阻擋／冷卻", "skipped": "略過"}


def cell(value: object) -> str:
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")


def build_summary(result_file: Path, data_file: Path, currencies: list[str]) -> str:
    heading = "## FX Pulse 抓取摘要\n\n"
    try:
        report = json.loads(result_file.read_text())
        if report["status"] not in STATUSES:
            raise ValueError("Unexpected report status")
        start = date.fromisoformat(report["window"]["from"])
        end = date.fromisoformat(report["window"]["to"])
        if start > end:
            raise ValueError("Invalid window")
        selected = report["sources"]
        if (
            not isinstance(selected, list)
            or not selected
            or any(s not in SOURCES for s in selected)
        ):
            raise ValueError("Invalid sources")
        results = report["results"]
        if not isinstance(results, dict) or any(not isinstance(r, dict) for r in results.values()):
            raise ValueError("Invalid results")
    except (OSError, ValueError, KeyError, TypeError):
        return heading + (
            "執行結果：無有效報告，無法確認是否完成。\n\n"
            "資料完整度：無法確認本次日期範圍；不將既有資料視為本次更新成功。\n"
        )

    text = heading + f"日期範圍：{start}～{end}（UTC 日期）\n\n"
    text += f"執行結果：{STATUSES[report['status']]}（與資料完整度分開判定）\n\n"
    try:
        payload = RatesPayload.model_validate_json(data_file.read_text())
    except (OSError, ValueError):
        return text + "資料完整度：匯率檔缺失或無效，無法計算。\n"

    rows = []
    total_remaining = 0
    for source in SOURCES:
        if source not in selected:
            continue
        expected = available = skipped = 0
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            if source == "JCB" and day.weekday() >= 5:
                skipped += 1
                continue
            expected += len(currencies)
            entries = payload.rates.get(day.isoformat(), {}).get(source, {})
            available += len(set(currencies) & entries.keys())
        remaining = expected - available
        total_remaining += remaining
        result = results.get(source, {})
        # No request is made for complete sources during backfill, even on a failed run.
        status = STATUSES.get(result.get("status"), "未記錄")
        if expected == 0:
            status = "略過（週末）"
        elif source not in results and report.get("mode") == "backfill" and remaining == 0:
            status = "無需回補"
        saved = result.get("currencies_saved")
        saved_text = str(saved) if type(saved) is int and saved >= 0 else "未記錄"
        if status.startswith("略過") or status == "無需回補":
            saved_text = "0"
        cooldown = "—"
        if result.get("next_retry_at"):
            try:
                retry = datetime.fromisoformat(result["next_retry_at"])
                cooldown = f"下次可重試：{retry.isoformat()}"
            except (ValueError, TypeError):
                cooldown = "重試時間無效"
        rows.append(
            f"| {source} | {status} | {saved_text} | {available}/{expected} | {remaining} "
            f"| {skipped} | {cell(cooldown)} |"
        )
    text += (
        f"資料完整度：{'完整' if total_remaining == 0 else '仍有缺漏'}；"
        f"剩餘 {total_remaining} 筆日期／來源／幣別。\n\n"
        "| 來源 | 本次狀態 | 本次已取得／補回並保存 | 區間已有／應有 "
        "| 剩餘缺漏 | 週末略過天數 | 冷卻資訊 |\n"
        "| --- | --- | ---: | ---: | ---: | ---: | --- |\n"
    )
    return (
        text
        + "\n".join(rows)
        + (
            "\n\n數量以日期／來源／幣別計算，區間已有資料包含先前保存的資料。"
            "JCB 週末依現有策略略過，不列入應有數；有效部分資料仍保留。\n"
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-file", type=Path, default=Path("scrape_result.json"))
    parser.add_argument("--data-file", type=Path, default=settings.data_file)
    args = parser.parse_args()
    summary = build_summary(args.result_file, args.data_file, settings.currencies)
    output = os.environ.get("GITHUB_STEP_SUMMARY")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(summary)
    else:
        print(summary)


if __name__ == "__main__":
    main()
