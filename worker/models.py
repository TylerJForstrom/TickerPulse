"""The unified post schema every adapter normalizes into."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


@dataclass
class Post:
    id: str                      # "<platform>:<native id>" — globally unique
    platform: str                # reddit | stocktwits | bluesky | hackernews | rss | sample
    text: str
    author: str
    timestamp: datetime          # always tz-aware UTC
    engagement: int = 0          # upvotes + likes + reposts, platform-weighted
    tickers: list[str] = field(default_factory=list)
    lang: str = "en"
    url: str = ""
    source: str = ""             # subreddit / feed name / venue detail
    sentiment: str | None = None         # bull | bear | neutral
    sentiment_score: float | None = None  # -1 .. +1
    topic_id: int | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        else:
            self.timestamp = self.timestamp.astimezone(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Post":
        d = dict(d)
        ts = d["timestamp"]
        if isinstance(ts, str):
            d["timestamp"] = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        known = {f for f in cls.__dataclass_fields__}  # tolerate extra keys
        return cls(**{k: v for k, v in d.items() if k in known})


def dedupe(posts: list[Post]) -> list[Post]:
    """Drop duplicate ids, keeping the highest-engagement copy."""
    best: dict[str, Post] = {}
    for p in posts:
        cur = best.get(p.id)
        if cur is None or p.engagement > cur.engagement:
            best[p.id] = p
    return sorted(best.values(), key=lambda p: p.timestamp)
