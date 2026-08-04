"""Archive derived metrics to committed files before retention pruning deletes them.

The free-tier database keeps only ~30 days (see pgsink.prune) and the trends
snapshot is replaced every run — without this stage, TickerPulse's history is
unrecoverable, which silently destroys future backtest data.

DURABILITY MODEL: the pipeline runs on GitHub Actions, whose runner disk is
destroyed after every run — so files written here are only durable because the
workflow commits `archive/` back to the repository. The checkout at the start
of each run restores previously archived files, which is what makes the
exists-check idempotent across ephemeral runners. Local runs get the same
behavior via the working tree.

Each completed UTC day of `ticker_buckets` is written once (gzipped JSONL);
`ticker_trends` gets one first-run-of-the-day sample file. Files already
present are never rewritten, so a multi-week outage self-heals as long as it
is shorter than the prune window (~30 days of slack vs daily archiving).

Archive layout (default ./archive, override TICKERPULSE_ARCHIVE_DIR):
    archive/ticker_buckets/YYYY-MM-DD.jsonl.gz   one row per (ticker, bucket)
    archive/ticker_trends/YYYY-MM-DD.jsonl.gz    daily snapshot sample
    archive/author_daily/YYYY-MM-DD.jsonl.gz     one row per (author_hash, ticker)
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os


def _write_jsonl_gz(path: str, rows: list[dict]) -> None:
    tmp = path + ".tmp"
    # mtime=0 keeps the gzip output byte-identical for identical rows, so
    # re-archiving after a partial failure can never produce a spurious diff.
    with gzip.GzipFile(tmp, "wb", mtime=0) as fh:
        for row in rows:
            fh.write((json.dumps(row, sort_keys=True, default=str) + "\n").encode("utf-8"))
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
        day = (
            start if isinstance(start, dt.datetime) else dt.datetime.fromisoformat(str(start))
        ).date()
        if day >= today:
            continue
        by_day.setdefault(day, []).append(row)
    written: dict[str, int] = {}
    for day, day_rows in sorted(by_day.items()):
        path = os.path.join(bucket_dir, f"{day.isoformat()}.jsonl.gz")
        if os.path.exists(path):
            continue
        day_rows.sort(key=lambda r: (str(r.get("ticker")), str(r.get("bucket_start"))))
        _write_jsonl_gz(path, day_rows)
        written[day.isoformat()] = len(day_rows)
    return written


def export_trends_snapshot(rows: list[dict], out_dir: str, today: dt.date | None = None) -> int:
    """Write one trends sample per day (first run of the day wins). On the
    ephemeral Actions runner, only committed files persist — a same-day
    overwrite would never survive to the next run anyway, so the first
    committed sample is the day's record."""
    today = today or dt.datetime.now(dt.UTC).date()
    trends_dir = os.path.join(out_dir, "ticker_trends")
    os.makedirs(trends_dir, exist_ok=True)
    path = os.path.join(trends_dir, f"{today.isoformat()}.jsonl.gz")
    if os.path.exists(path):
        return 0
    rows = sorted(rows, key=lambda r: str(r.get("ticker")))
    _write_jsonl_gz(path, rows)
    return len(rows)


def author_hash(platform: str, author: str) -> str:
    """Stable pseudonym for an author, scoped per platform so the same handle
    on two platforms never links. Unsalted on purpose: the aggregates must be
    joinable across days and runs (track-record accrual), and the archived
    rows never carry the raw username."""
    return hashlib.sha256(f"{platform}:{author}".encode("utf-8")).hexdigest()[:16]


def export_author_daily(rows: list[dict], out_dir: str, today: dt.date | None = None) -> dict[str, int]:
    """Aggregate posts into per-(author_hash, ticker, day) stance rows and
    write completed past days that have no archive file yet — the raw
    material for author track-record weighting once months accrue. Pure:
    rows in (platform/author/tickers/sentiment/sentiment_score/created_at),
    files out. Today's partial day is skipped; raw usernames are hashed and
    never written."""
    today = today or dt.datetime.now(dt.UTC).date()
    author_dir = os.path.join(out_dir, "author_daily")
    os.makedirs(author_dir, exist_ok=True)
    # (day, author_hash, platform, ticker) -> stance accumulator
    aggs: dict[tuple, dict] = {}
    for row in rows:
        created = row["created_at"]
        if not isinstance(created, dt.datetime):
            created = dt.datetime.fromisoformat(str(created))
        day = created.date()
        if day >= today:
            continue
        hashed = author_hash(row["platform"], row["author"])
        for ticker in row.get("tickers") or []:
            key = (day, hashed, row["platform"], ticker)
            agg = aggs.setdefault(key, {
                "author": hashed, "platform": row["platform"], "ticker": ticker,
                "posts": 0, "bull": 0, "bear": 0, "neutral": 0,
                "_score_sum": 0.0, "_score_n": 0,
            })
            agg["posts"] += 1
            sentiment = row.get("sentiment")
            if sentiment in ("bull", "bear", "neutral"):
                agg[sentiment] += 1
            if row.get("sentiment_score") is not None:
                agg["_score_sum"] += float(row["sentiment_score"])
                agg["_score_n"] += 1
    by_day: dict[dt.date, list[dict]] = {}
    for (day, _, _, _), agg in aggs.items():
        n = agg.pop("_score_n")
        total = agg.pop("_score_sum")
        agg["sentiment_avg"] = round(total / n, 6) if n else None
        by_day.setdefault(day, []).append(agg)
    written: dict[str, int] = {}
    for day, day_rows in sorted(by_day.items()):
        path = os.path.join(author_dir, f"{day.isoformat()}.jsonl.gz")
        if os.path.exists(path):
            continue
        day_rows.sort(key=lambda r: (r["author"], r["ticker"]))
        _write_jsonl_gz(path, day_rows)
        written[day.isoformat()] = len(day_rows)
    return written


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
    authors = _fetch_dicts(
        conn,
        "select platform, author, tickers, sentiment, sentiment_score, created_at "
        "from posts where created_at < date_trunc('day', now()) "
        "and tickers is not null and array_length(tickers, 1) > 0",
    )
    written = export_buckets(buckets, out_dir)
    trend_count = export_trends_snapshot(trends, out_dir)
    author_days = export_author_daily(authors, out_dir)
    return {
        "bucket_days_written": written,
        "trend_rows": trend_count,
        "author_days_written": author_days,
    }
