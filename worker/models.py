"""The unified post schema every adapter normalizes into."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict, replace
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


_URL_RE = re.compile(r"https?://\S+")
_COPYPASTA_MIN_CHARS = 100  # below this, repetition is genuine breadth, not a campaign


def copypasta_fingerprint(text: str) -> str | None:
    """Fingerprint long-form text for cross-author/platform duplicate collapse.

    Returns None for short text: short repeated phrases ("NVDA to the moon")
    are genuine breadth and must not collapse. Normalization — lowercase,
    URLs stripped, whitespace collapsed — makes case tweaks and appended
    spam links hash identically; anything sneakier than that survives, which
    is the honest limit of an exact-after-normalization match.
    """
    normalized = " ".join(_URL_RE.sub(" ", text).lower().split())
    if len(normalized) < _COPYPASTA_MIN_CHARS:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def collapse_near_duplicates(posts: list[Post]) -> list[Post]:
    """Collapse long-form copypasta (spam campaigns, cross-platform paste
    bots) to ONE mention: the earliest post is the origin and keeps the
    group's summed engagement, so amplification still registers as reach
    without inflating the mention count. Short posts pass through untouched.
    Input posts are never mutated; the collapsed group is emitted at the
    position of its first appearance."""
    groups: dict[str, list[Post]] = {}
    ordered: list[tuple[str | None, Post]] = []
    for p in posts:
        fp = copypasta_fingerprint(p.text)
        ordered.append((fp, p))
        if fp is not None:
            groups.setdefault(fp, []).append(p)
    emitted: set[str] = set()
    kept: list[Post] = []
    for fp, p in ordered:
        if fp is None:
            kept.append(p)
        elif fp not in emitted:
            emitted.add(fp)
            group = groups[fp]
            origin = min(group, key=lambda g: g.timestamp)
            kept.append(replace(origin, engagement=sum(g.engagement for g in group)))
    return kept
