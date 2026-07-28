"""Archive derived metrics to local files before retention pruning deletes them.

The free-tier database keeps only ~30 days (see pgsink.prune) and the trends
snapshot is replaced every run — without this stage, TickerPulse's history is
unrecoverable, which silently destroys future backtest data. Each completed UTC
day of `ticker_buckets` is written once to a dated JSONL file; the day's last
`ticker_trends` snapshot survives as one file per day. Files already on disk
are never rewritten, so the stage is idempotent and a multi-week outage
self-heals as long as it is shorter than the prune window.

Archive layout (default ./archive, override TICKERPULSE_ARCHIVE_DIR):
    archive/ticker_buckets/YYYY-MM-DD.jsonl   one row per (ticker, bucket)
    archive/ticker_trends/YYYY-MM-DD.jsonl    last snapshot written that day
"""

from __future__ import annotations

import datetime as dt
import json
import os


def _write_jsonl(path: str, rows: list[dict]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    os.replace(tmp, path)


def export_buckets(rows: list[dict], out_dir: str, today: dt.date | None = None) -> dict[str, int]:
    """Write completed past days that have no archive file yet. Pure: rows in,
    files out. Today's partial day is skipped (it gets archived tomorrow)."""
    today = today or dt.datetime.now(dt.UTC).date()
    bucket_dir = os.path.join(out_dir, "ticker_buckets")
    os.makedirs(bucket_dir, exist_ok=True)
    by_day: dict[dt.date, list[dict]] = {}
    for row in rows:
        start = row["bucket_start"]
        day = (start if isinstance(start, dt.datetime) else dt.datetime.fromisoformat(str(start))).date()
        if day >= today:
            continue
        by_day.setdefault(day, []).append(row)
    written: dict[str, int] = {}
    for day, day_rows in sorted(by_day.items()):
        path = os.path.join(bucket_dir, f"{day.isoformat()}.jsonl")
        if os.path.exists(path):
            continue
        day_rows.sort(key=lambda r: (str(r.get("ticker")), str(r.get("bucket_start"))))
        _write_jsonl(path, day_rows)
        written[day.isoformat()] = len(day_rows)
    return written


def export_trends_snapshot(rows: list[dict], out_dir: str, today: dt.date | None = None) -> int:
    """Write today's trends snapshot, overwriting earlier runs the same day —
    the last run of each day is the state that survives."""
    today = today or dt.datetime.now(dt.UTC).date()
    trends_dir = os.path.join(out_dir, "ticker_trends")
    os.makedirs(trends_dir, exist_ok=True)
    rows = sorted(rows, key=lambda r: str(r.get("ticker")))
    _write_jsonl(os.path.join(trends_dir, f"{today.isoformat()}.jsonl"), rows)
    return len(rows)


def _fetch_dicts(conn, query: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(query)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def archive(conn, out_dir: str) -> dict[str, object]:
    """Run both exports against the live tables. Called just before prune."""
    buckets = _fetch_dicts(
        conn,
        "select * from ticker_buckets where bucket_start < date_trunc('day', now())",
    )
    trends = _fetch_dicts(conn, "select * from ticker_trends")
    written = export_buckets(buckets, out_dir)
    trend_count = export_trends_snapshot(trends, out_dir)
    return {"bucket_days_written": written, "trend_rows": trend_count}
