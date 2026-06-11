"""Generic CSV / JSON loader — offline ingestion and the demo sample set.

Accepts any file whose rows/objects carry at least `text` and `timestamp`;
everything else is mapped with forgiving fallbacks so real-world exports
(Reddit dumps, Kaggle sets, StockTwits exports) load without preprocessing.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from worker.ingest.base import Adapter
from worker.models import Post

# Field aliases seen in common exports → unified schema.
ALIASES = {
    "text": ["text", "body", "title", "content", "message", "selftext"],
    "author": ["author", "user", "username", "screen_name"],
    "timestamp": ["timestamp", "created_at", "created_utc", "date", "time"],
    "engagement": ["engagement", "score", "ups", "likes", "upvotes", "points"],
    "url": ["url", "permalink", "link"],
    "platform": ["platform", "source_platform", "site"],
    "source": ["source", "subreddit", "feed", "channel"],
    "id": ["id", "post_id", "uid"],
    "tickers": ["tickers", "symbols", "cashtags"],
    "lang": ["lang", "language"],
}


def _pick(row: dict, field: str):
    for key in ALIASES[field]:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _parse_ts(value) -> datetime:
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.replace(".", "", 1).isdigit()):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def row_to_post(row: dict, default_platform: str = "sample") -> Post | None:
    text = _pick(row, "text")
    ts = _pick(row, "timestamp")
    if not text or ts is None:
        return None
    platform = _pick(row, "platform") or default_platform
    native_id = _pick(row, "id") or hashlib.sha1(
        f"{text}{ts}".encode()
    ).hexdigest()[:16]
    tickers = _pick(row, "tickers") or []
    if isinstance(tickers, str):
        tickers = [t.strip().upper().lstrip("$") for t in tickers.split(",") if t.strip()]
    try:
        engagement = int(float(_pick(row, "engagement") or 0))
    except (TypeError, ValueError):
        engagement = 0
    return Post(
        id=f"{platform}:{native_id}",
        platform=platform,
        text=str(text),
        author=str(_pick(row, "author") or "unknown"),
        timestamp=_parse_ts(ts),
        engagement=engagement,
        tickers=list(tickers),
        lang=str(_pick(row, "lang") or "en"),
        url=str(_pick(row, "url") or ""),
        source=str(_pick(row, "source") or ""),
    )


class FileLoader(Adapter):
    name = "file"

    def __init__(self, path: str | Path, platform: str = "sample"):
        self.path = Path(path)
        self.platform = platform

    def available(self) -> bool:
        return self.path.exists()

    def fetch(self) -> Iterable[Post]:
        rows: list[dict]
        if self.path.suffix.lower() == ".csv":
            with open(self.path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        else:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            rows = data["posts"] if isinstance(data, dict) and "posts" in data else data
        for row in rows:
            post = row_to_post(row, default_platform=self.platform)
            if post:
                yield post
