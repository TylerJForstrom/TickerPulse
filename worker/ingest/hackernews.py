"""Hacker News adapter — Algolia search API, keyless. Secondary source for
tech-adjacent finance chatter (earnings threads, market stories)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import requests

from worker.ingest.base import Adapter
from worker.models import Post

API = "https://hn.algolia.com/api/v1/search_by_date"
QUERIES = ["stock", "earnings", "nvidia", "fed rates", "ipo", "bitcoin"]


class HackerNewsAdapter(Adapter):
    name = "hackernews"

    def available(self) -> bool:
        return True

    def fetch(self) -> Iterable[Post]:
        seen: set[str] = set()
        for q in QUERIES:
            try:
                resp = requests.get(
                    API, params={"query": q, "tags": "story", "hitsPerPage": 30},
                    timeout=30,
                )
                if resp.status_code != 200:
                    continue
                for hit in resp.json().get("hits", []):
                    oid = hit["objectID"]
                    if oid in seen or not hit.get("title"):
                        continue
                    seen.add(oid)
                    yield Post(
                        id=f"hackernews:{oid}",
                        platform="hackernews",
                        source="hackernews",
                        author=hit.get("author", "unknown"),
                        text=hit["title"],
                        timestamp=datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc),
                        engagement=int(hit.get("points") or 0) + int(hit.get("num_comments") or 0),
                        url=hit.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                    )
            except Exception as exc:
                print(f"  hackernews '{q}' failed: {exc}")
