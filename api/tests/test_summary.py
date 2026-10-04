"""Summary fixtures are local; never scrape or post externally."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "summarize_scrape", Path(__file__).parents[1] / "scripts" / "summarize_scrape.py"
)
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def fixtures(
    tmp_path, *, status="ok", results=None, mode=None, start="2026-10-02", end="2026-10-02"
):
    report = {
        "status": status,
        "window": {"from": start, "to": end},
        "sources": ["VISA", "Mastercard", "JCB"],
        "results": results
        if results is not None
        else {s: {"status": "ok", "currencies_saved": 1} for s in summary.SOURCES},
        "mode": mode,
    }
    data = {
        "meta": {"base": "TWD", "currencies": ["USD"], "last_updated": ""},
        "rates": {
            "2026-10-02": {s: {"USD": {"rate": 30, "reverse": 1 / 30}} for s in summary.SOURCES}
        },
    }
    result_path, data_path = tmp_path / "result.json", tmp_path / "rates.json"
    result_path.write_text(json.dumps(report))
    data_path.write_text(json.dumps(data))
    return result_path, data_path


def test_complete_daily_data_is_separate_from_execution(tmp_path):
    paths = fixtures(tmp_path)
    text = summary.build_summary(*paths, ["USD"])
    assert "執行結果：完成" in text
    assert "資料完整度：完整" in text
    assert "| VISA | 完成 | 1 | 1/1 | 0 |" in text


def test_partial_save_and_cooldown_are_reported_without_changing_rates(tmp_path):
    paths = fixtures(
        tmp_path,
        status="blocked",
        results={
            "VISA": {
                "status": "blocked",
                "currencies_saved": 1,
                "next_retry_at": "2026-10-03T09:00:00+00:00",
            }
        },
    )
    before = paths[1].read_bytes()
    text = summary.build_summary(*paths, ["USD", "JPY"])
    assert "執行結果：阻擋／冷卻" in text
    assert "剩餘 3 筆" in text
    assert "| VISA | 阻擋／冷卻 | 1 | 1/2 | 1 |" in text
    assert "2026-10-03T09:00:00+00:00" in text
    assert paths[1].read_bytes() == before


def test_failed_refresh_can_leave_complete_existing_data(tmp_path):
    paths = fixtures(
        tmp_path, status="error", results={"VISA": {"status": "error", "currencies_saved": 0}}
    )
    text = summary.build_summary(*paths, ["USD"])
    assert "執行結果：失敗" in text
    assert "資料完整度：完整" in text
    assert "| VISA | 失敗 | 0 | 1/1 |" in text


def test_backfill_uses_report_window_and_counts_weekend_skips(tmp_path):
    paths = fixtures(tmp_path, mode="backfill", start="2026-10-02", end="2026-10-04", results={})
    text = summary.build_summary(*paths, ["USD"])
    assert "2026-10-02～2026-10-04" in text
    assert "| JCB | 無需回補 | 0 | 1/1 | 0 | 2 |" in text
    assert "| VISA | 未記錄 | 未記錄 | 1/3 | 2 |" in text
    assert "剩餘 4 筆" in text


def test_weekend_daily_jcb_is_not_missing(tmp_path):
    paths = fixtures(tmp_path, start="2026-10-03", end="2026-10-03")
    text = summary.build_summary(*paths, ["USD"])
    assert "| JCB | 略過（週末） | 0 | 0/0 | 0 | 1 |" in text
    assert "剩餘 2 筆" in text


@pytest.mark.parametrize("contents", [None, "invalid", "{}", "[]", '{"status": "ok"}'])
def test_missing_or_invalid_report_does_not_claim_success(tmp_path, contents):
    paths = fixtures(tmp_path)
    if contents is None:
        paths[0].unlink()
    else:
        paths[0].write_text(contents)
    text = summary.build_summary(*paths, ["USD"])
    assert "無有效報告" in text
    assert "資料完整度：完整" not in text


def test_invalid_data_file_keeps_execution_but_does_not_claim_coverage(tmp_path):
    paths = fixtures(tmp_path)
    paths[1].write_text("{}")
    text = summary.build_summary(*paths, ["USD"])
    assert "執行結果：完成" in text
    assert "匯率檔缺失或無效" in text


def test_main_appends_to_actions_step_summary(tmp_path, monkeypatch):
    result_path, data_path = fixtures(tmp_path)
    output = tmp_path / "step-summary.md"
    output.write_text("Previous step\n")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(output))
    monkeypatch.setattr(summary.settings, "currencies", ["USD"])
    monkeypatch.setattr(
        "sys.argv",
        ["summarize_scrape.py", "--result-file", str(result_path), "--data-file", str(data_path)],
    )
    summary.main()
    text = output.read_text()
    assert text.startswith("Previous step\n## FX Pulse")
    assert "| VISA | 完成 | 1 | 1/1 | 0 |" in text
