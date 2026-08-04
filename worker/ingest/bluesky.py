"""Bluesky adapter — AT Protocol searchPosts over finance terms.

Uses an app password (free, from bsky.app settings → App Passwords).
Searches a rotation of finance queries, paginating each back through the
scheduler-gap window (see base.drain_pages); broader chatter than the
finance-native sources, useful for diffusion tracking."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Iterable, Iterator

import requests

from worker.config import settings
from worker.ingest.base import Adapter, drain_pages
from worker.models import Post

PDS = "https://bsky.social/xrpc"
QUERIES = [
    "stock market", "stocks earnings", "$SPY", "$NVDA", "$TSLA", "$BTC",
    "fed rate cut", "short squeeze", "bull market", "bitcoin etf",
]

PAGE_LIMIT = 100   # searchPosts max per page
MAX_PAGES = 3      # 300 posts of depth per query; 10 queries = ≤30 requests


class BlueskyAdapter(Adapter):
    name = "bluesky"

    def available(self) -> bool:
        return bool(settings.bluesky_handle and settings.bluesky_app_password)

    def _session(self) -> dict:
        resp = requests.post(
            f"{PDS}/com.atproto.server.createSession",
            json={"identifier": settings.bluesky_handle,
                  "password": settings.bluesky_app_password},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, item: dict) -> Post:
        uri = item["uri"]
        record = item.get("record", {})
        handle = (item.get("author") or {}).get("handle", "unknown")
        rkey = uri.rsplit("/", 1)[-1]
        # sha1 of the at:// URI, not builtin hash(): str hashing is salted
        # per process, so hash()-derived ids changed every run and re-fetches
        # (which gap-tolerant pagination multiplies) piled up duplicate rows.
        uid = hashlib.sha1(uri.encode("utf-8")).hexdigest()[:8]
        return Post(
            id=f"bluesky:{rkey}:{uid}",
            platform="bluesky",
            source="bluesky",
            author=handle,
            text=record.get("text", ""),
            timestamp=datetime.fromisoformat(
                record.get("createdAt", item.get("indexedAt")).replace("Z", "+00:00")
            ),
            engagement=int(item.get("likeCount", 0))
            + int(item.get("repostCount", 0)) * 2,
            url=f"https://bsky.app/profile/{handle}/post/{rkey}",
            lang=(record.get("langs") or ["en"])[0],
        )

    def _pages(self, q: str, headers: dict) -> Iterator[list[Post]]:
        cursor = None
        while True:
            params = {"q": q, "limit": PAGE_LIMIT, "sort": "latest", "lang": "en"}
            if cursor:
                params["cursor"] = cursor
            resp = requests.get(
                f"{PDS}/app.bsky.feed.searchPosts",
                params=params, headers=headers, timeout=30,
            )
            if resp.status_code != 200:
                print(f"  bluesky '{q}': HTTP {resp.status_code}")
                return
            payload = resp.json()
            yield [self._post(item) for item in payload.get("posts", [])]
            cursor = payload.get("cursor")
            if not cursor:
                return

    def fetch(self) -> Iterable[Post]:
        sess = self._session()
        headers = {"Authorization": f"Bearer {sess['accessJwt']}"}
        seen: set[str] = set()
        for q in QUERIES:
            try:
                posts = drain_pages(
                    self._pages(q, headers),
                    lookback_hours=settings.ingest_lookback_hours,
                    max_pages=MAX_PAGES,
                    label=f"bluesky '{q}'",
                )
            except Exception as exc:
                print(f"  bluesky '{q}' failed: {exc}")
                continue
            for post in posts:
                if post.id in seen:
                    continue
                seen.add(post.id)
                yield post
