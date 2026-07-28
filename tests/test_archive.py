"""The archive sink must preserve history idempotently before pruning."""

import datetime as dt
import json

from worker.sinks.archive import export_buckets, export_trends_snapshot

TODAY = dt.date(2026, 7, 28)


def bucket(ticker, day_str, hour, mentions=5):
    return {
        "ticker": ticker,
        "bucket_start": dt.datetime.fromisoformat(f"{day_str}T{hour:02d}:00:00+00:00"),
        "bucket_minutes": 60,
        "mentions": mentions,
        "sentiment_avg": 0.4,
        "platforms": {"reddit": mentions},
    }


def test_completed_days_written_today_skipped(tmp_path):
    rows = [
        bucket("AAPL", "2026-07-26", 14),
        bucket("AAPL", "2026-07-27", 9),
        bucket("AAPL", "2026-07-28", 10),  # today: partial, must be skipped
    ]
    written = export_buckets(rows, str(tmp_path), today=TODAY)
    assert sorted(written) == ["2026-07-26", "2026-07-27"]
    assert not (tmp_path / "ticker_buckets" / "2026-07-28.jsonl").exists()
    line = (tmp_path / "ticker_buckets" / "2026-07-26.jsonl").read_text().strip()
    assert json.loads(line)["mentions"] == 5


def test_existing_files_never_rewritten(tmp_path):
    rows = [bucket("AAPL", "2026-07-26", 14)]
    export_buckets(rows, str(tmp_path), today=TODAY)
    path = tmp_path / "ticker_buckets" / "2026-07-26.jsonl"
    before = path.read_text()
    export_buckets([bucket("AAPL", "2026-07-26", 14, mentions=999)], str(tmp_path), today=TODAY)
    assert path.read_text() == before  # first archive of a day is final


def test_trends_snapshot_last_run_of_day_wins(tmp_path):
    export_trends_snapshot([{"ticker": "AAPL", "mentions": 10}], str(tmp_path), today=TODAY)
    count = export_trends_snapshot(
        [{"ticker": "AAPL", "mentions": 22}, {"ticker": "NVDA", "mentions": 8}],
        str(tmp_path),
        today=TODAY,
    )
    assert count == 2
    lines = (tmp_path / "ticker_trends" / "2026-07-28.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["mentions"] == 22
