"""Mastodon adapter — public hashtag timelines, keyless.

Public timelines on the flagship instance are readable without auth, and
paginate by max_id back through the scheduler-gap window (see
base.drain_pages). Finance volume is modest but it widens the social
diffusion picture."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from datetime import datetime

import requests

from worker.config import settings
from worker.ingest.base import Adapter, drain_pages
from worker.models import Post

INSTANCE = "https://mastodon.social"
TAGS = ["stocks", "stockmarket", "investing", "bitcoin", "crypto"]
HEADERS = {"User-Agent": "TickerPulse/1.0 (research project)"}
TAG_RE = re.compile(r"<[^>]+>")

PAGE_LIMIT = 40  # API max for public timelines
MAX_PAGES = 5  # 200 statuses of depth per tag; 5 tags = ≤25 requests


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", html)).strip()


def _status_ts(status: dict) -> datetime:
    return datetime.fromisoformat(status["created_at"])


class MastodonAdapter(Adapter):
    name = "mastodon"

    def available(self) -> bool:
        return True

    def _pages(self, tag: str) -> Iterator[list[dict]]:
        max_id = None
        while True:
            params = {"limit": PAGE_LIMIT}
            if max_id:
                params["max_id"] = max_id
            resp = requests.get(
                f"{INSTANCE}/api/v1/timelines/tag/{tag}",
                params=params,
                headers=HEADERS,
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"  mastodon #{tag}: HTTP {resp.status_code}")
                return
            statuses = resp.json()
            yield statuses
            if len(statuses) < PAGE_LIMIT:
                return  # short page = timeline exhausted
            max_id = statuses[-1]["id"]

    def fetch(self) -> Iterable[Post]:
        seen: set[str] = set()
        for tag in TAGS:
            try:
                # Window coverage is judged on raw statuses, pre-filter: a
                # page of non-English chatter still proves the hours it spans
                # were walked, so filtering can't fake an exhausted listing.
                statuses = drain_pages(
                    self._pages(tag),
                    lookback_hours=settings.ingest_lookback_hours,
                    max_pages=MAX_PAGES,
                    label=f"mastodon #{tag}",
                    ts=_status_ts,
                )
            except Exception as exc:
                print(f"  mastodon #{tag} failed: {exc}")
                continue
            for status in statuses:
                sid = status.get("id")
                if not sid or sid in seen:
                    continue
                seen.add(sid)
                text = _strip_html(status.get("content", ""))
                if len(text) < 10:
                    continue
                lang = status.get("language") or "en"
                if lang != "en":
                    continue
                yield Post(
                    id=f"mastodon:{sid}",
                    platform="mastodon",
                    source=f"#{tag}",
                    author=(status.get("account") or {}).get("acct", "unknown"),
                    text=text[:1000],
                    timestamp=_status_ts(status),
                    engagement=int(status.get("favourites_count", 0))
                    + int(status.get("reblogs_count", 0)) * 2,
                    url=status.get("url", ""),
                    lang=lang,
                )
