"""The unified post schema every adapter normalizes into."""

from __future__ import annotations

import hashlib
import re
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


_URL_RE = re.compile(r"https?://\S+")
_TOKEN_RE = re.compile(r"[a-z0-9$]+")

# Normalized texts shorter than this never fingerprint: repeating a short
# phrase ("NVDA to the moon") is genuine breadth, not a paste campaign.
COPYPASTA_MIN_CHARS = 80


def copypasta_fingerprint(text: str) -> str | None:
    """Fingerprint long-form text for copypasta collapse, or None if short.

    Normalization strips URLs (spam variants differ only by tracking links),
    lowercases, and collapses everything but word/cashtag tokens, so casing
    and punctuation games don't defeat the match."""
    tokens = _TOKEN_RE.findall(_URL_RE.sub(" ", text.lower()))
    normalized = " ".join(tokens)
    if len(normalized) < COPYPASTA_MIN_CHARS:
        return None
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def collapse_near_duplicates(posts: list[Post]) -> list[Post]:
    """Collapse long-form copypasta into one origin mention per fingerprint.

    The earliest copy is the origin and survives; later copies are dropped
    with their engagement folded into the origin, so a spam campaign still
    registers amplification but stops inflating mention counts and author
    breadth. Short posts pass through untouched."""
    out: list[Post] = []
    groups: dict[str, list[Post]] = {}
    for p in posts:
        fp = copypasta_fingerprint(p.text)
        if fp is None:
            out.append(p)
        else:
            groups.setdefault(fp, []).append(p)
    for copies in groups.values():
        copies.sort(key=lambda p: p.timestamp)
        origin = copies[0]
        origin.engagement = sum(c.engagement for c in copies)
        out.append(origin)
    return out
