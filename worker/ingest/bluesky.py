"""Bluesky adapter — AT Protocol searchPosts over finance terms.

Uses an app password (free, from bsky.app settings → App Passwords).
Searches a rotation of finance queries; broader chatter than the
finance-native sources, useful for diffusion tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

import requests

from worker.config import settings
from worker.ingest.base import Adapter
from worker.models import Post

PDS = "https://bsky.social/xrpc"
QUERIES = [
    "stock market", "stocks earnings", "$SPY", "$NVDA", "$TSLA", "$BTC",
    "fed rate cut", "short squeeze", "bull market", "bitcoin etf",
]


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

    def fetch(self) -> Iterable[Post]:
        sess = self._session()
        headers = {"Authorization": f"Bearer {sess['accessJwt']}"}
        seen: set[str] = set()
        for q in QUERIES:
            try:
                resp = requests.get(
                    f"{PDS}/app.bsky.feed.searchPosts",
                    params={"q": q, "limit": 50, "sort": "latest", "lang": "en"},
                    headers=headers, timeout=30,
                )
                if resp.status_code != 200:
                    continue
                for item in resp.json().get("posts", []):
                    uri = item["uri"]
                    if uri in seen:
                        continue
                    seen.add(uri)
                    record = item.get("record", {})
                    handle = (item.get("author") or {}).get("handle", "unknown")
                    rkey = uri.rsplit("/", 1)[-1]
                    yield Post(
                        id=f"bluesky:{uri.split('/')[-1]}:{hash(uri) & 0xffffff:x}",
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
            except Exception as exc:
                print(f"  bluesky '{q}' failed: {exc}")
