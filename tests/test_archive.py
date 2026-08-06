"""The archive sink must preserve history idempotently before pruning."""

import datetime as dt
import gzip
import json

from worker.sinks.archive import (
    export_author_daily,
    export_buckets,
    export_trends_snapshot,
)


def read_gz_lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


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
    assert not (tmp_path / "ticker_buckets" / "2026-07-28.jsonl.gz").exists()
    lines = read_gz_lines(tmp_path / "ticker_buckets" / "2026-07-26.jsonl.gz")
    assert json.loads(lines[0])["mentions"] == 5


def test_existing_files_never_rewritten(tmp_path):
    rows = [bucket("AAPL", "2026-07-26", 14)]
    export_buckets(rows, str(tmp_path), today=TODAY)
    path = tmp_path / "ticker_buckets" / "2026-07-26.jsonl.gz"
    before = path.read_bytes()
    export_buckets(
        [bucket("AAPL", "2026-07-26", 14, mentions=999)], str(tmp_path), today=TODAY
    )
    assert path.read_bytes() == before  # first archive of a day is final


def test_aligned_bucket_series_boundaries_are_stable_across_runs():
    """Persisted buckets must use clock-hour boundaries so the DB primary key
    is identical run-to-run (drifting anchors would accumulate junk rows)."""
    from worker.metrics.trends import bucket_series

    aligned_now = dt.datetime(2026, 7, 28, 15, 0, tzinfo=dt.UTC)
    series_a = bucket_series([], "AAPL", 60, now=aligned_now)
    series_b = bucket_series([], "AAPL", 60, now=aligned_now)
    starts = [row["bucket_start"] for row in series_a]
    assert starts == [row["bucket_start"] for row in series_b]
    assert all(s.endswith(":00:00+00:00") for s in starts)  # top-of-hour anchors


def author_row(day_str, hour=12, author="bob", tickers=("XYZ",), score=0.5):
    return {
        "platform": "reddit",
        "author": author,
        "tickers": list(tickers),
        "sentiment": "bull",
        "sentiment_score": score,
        "created_at": dt.datetime.fromisoformat(f"{day_str}T{hour:02d}:00:00+00:00"),
    }


def test_author_daily_existing_files_never_rewritten(tmp_path):
    export_author_daily([author_row("2026-07-26")], str(tmp_path), today=TODAY)
    path = tmp_path / "author_daily" / "2026-07-26.jsonl.gz"
    before = path.read_bytes()
    written = export_author_daily(
        [author_row("2026-07-26", score=-0.9)], str(tmp_path), today=TODAY
    )
    assert written == {}  # day already archived
    assert path.read_bytes() == before  # first archive of a day is final


def test_author_daily_output_is_byte_deterministic(tmp_path):
    rows = [
        author_row("2026-07-26", author=a, tickers=("XYZ", "ABC")) for a in ("z", "a")
    ]
    export_author_daily(rows, str(tmp_path / "one"), today=TODAY)
    export_author_daily(list(reversed(rows)), str(tmp_path / "two"), today=TODAY)
    p = "author_daily/2026-07-26.jsonl.gz"
    assert (tmp_path / "one" / p).read_bytes() == (tmp_path / "two" / p).read_bytes()


def test_trends_snapshot_first_run_of_day_wins(tmp_path):
    count = export_trends_snapshot(
        [{"ticker": "AAPL", "mentions": 10}], str(tmp_path), today=TODAY
    )
    assert count == 1
    second = export_trends_snapshot(
        [{"ticker": "AAPL", "mentions": 22}, {"ticker": "NVDA", "mentions": 8}],
        str(tmp_path),
        today=TODAY,
    )
    assert second == 0  # same-day sample already recorded; never rewritten
    lines = read_gz_lines(tmp_path / "ticker_trends" / "2026-07-28.jsonl.gz")
    assert len(lines) == 1
    assert json.loads(lines[0])["mentions"] == 10
