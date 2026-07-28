"""Copypasta collapse and author-aggregate tests."""

import datetime as dt

from worker.models import Post, collapse_near_duplicates, copypasta_fingerprint
from worker.sinks.archive import author_hash, export_author_daily

LONG_SPAM = (
    "HUGE news for $XYZ today, this is the next 100x play, management just "
    "announced a game changing partnership, load up before the crowd finds it"
)


def post(pid, text, author="a", platform="reddit", eng=1, hour=12):
    return Post(
        id=pid,
        platform=platform,
        text=text,
        author=author,
        timestamp=dt.datetime(2026, 7, 27, hour, tzinfo=dt.UTC),
        engagement=eng,
    )


def test_long_copypasta_collapses_across_authors_and_platforms():
    posts = [
        post("reddit:1", LONG_SPAM, author="og", eng=10, hour=9),
        post("reddit:2", LONG_SPAM + " http://spam.link", author="bot1", eng=5, hour=10),
        post("stocktwits:3", LONG_SPAM.upper(), author="bot2", platform="stocktwits", eng=7),
    ]
    kept = collapse_near_duplicates(posts)
    assert len(kept) == 1
    assert kept[0].id == "reddit:1"  # earliest = origin
    assert kept[0].engagement == 22  # amplification folded in


def test_short_repeated_phrases_are_left_alone():
    posts = [post(f"x:{i}", "NVDA to the moon", author=f"u{i}") for i in range(3)]
    assert len(collapse_near_duplicates(posts)) == 3
    assert copypasta_fingerprint("NVDA to the moon") is None


def test_author_daily_aggregates_and_privacy(tmp_path):
    rows = [
        {
            "platform": "reddit", "author": "deepvalue", "tickers": ["XYZ", "ABC"],
            "sentiment": "bull", "sentiment_score": 0.8,
            "created_at": dt.datetime(2026, 7, 26, 14, tzinfo=dt.UTC),
        },
        {
            "platform": "reddit", "author": "deepvalue", "tickers": ["XYZ"],
            "sentiment": "bear", "sentiment_score": -0.4,
            "created_at": dt.datetime(2026, 7, 26, 18, tzinfo=dt.UTC),
        },
        {   # today: must be skipped
            "platform": "reddit", "author": "deepvalue", "tickers": ["XYZ"],
            "sentiment": "bull", "sentiment_score": 0.9,
            "created_at": dt.datetime(2026, 7, 28, 9, tzinfo=dt.UTC),
        },
    ]
    written = export_author_daily(rows, str(tmp_path), today=dt.date(2026, 7, 28))
    assert written == {"2026-07-26": 2}  # XYZ and ABC rows for one author
    import gzip, json
    lines = gzip.open(tmp_path / "author_daily" / "2026-07-26.jsonl.gz", "rt").read().splitlines()
    xyz = next(json.loads(line) for line in lines if json.loads(line)["ticker"] == "XYZ")
    assert xyz["posts"] == 2 and xyz["bull"] == 1 and xyz["bear"] == 1
    assert abs(xyz["sentiment_avg"] - 0.2) < 1e-9
    assert "deepvalue" not in str(xyz)  # hashed, never raw


def test_author_hash_is_stable_and_platform_scoped():
    assert author_hash("reddit", "bob") == author_hash("reddit", "bob")
    assert author_hash("reddit", "bob") != author_hash("stocktwits", "bob")
