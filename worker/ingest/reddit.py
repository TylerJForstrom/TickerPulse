"""Reddit adapter — official OAuth API (application-only grant), ToS-compliant.

Reads /new + /hot from the configured finance subreddits. /new is paginated
back through the scheduler-gap window (see base.drain_pages) so dropped cron
ticks don't lose posts; /hot is a non-chronological engagement sample, so one
page is all it means. Engagement is score + comment count. Requires a free
"script" app from reddit.com/prefs/apps (client id + secret)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator

import requests

from worker.config import settings
from worker.ingest.base import Adapter, drain_pages
from worker.models import Post

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"

PAGE_LIMIT = 100  # API max per listing page
MAX_NEW_PAGES = 8  # 800 posts of /new depth per subreddit; worst case
# 5 subs x (8 new + 1 hot) + token = 46 requests/run,
# well inside the OAuth client-credentials quota


class RedditAdapter(Adapter):
    name = "reddit"

    def available(self) -> bool:
        return bool(settings.reddit_client_id and settings.reddit_client_secret)

    def _token(self) -> str:
        resp = requests.post(
            TOKEN_URL,
            auth=(settings.reddit_client_id, settings.reddit_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": settings.reddit_user_agent},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _post(self, d: dict, sub: str) -> Post:
        text = d.get("title", "")
        body = (d.get("selftext") or "")[:1000]
        if body and body not in ("[removed]", "[deleted]"):
            text = f"{text}. {body}"
        return Post(
            id=f"reddit:{d['id']}",
            platform="reddit",
            source=sub,
            author=d.get("author", "unknown"),
            text=text,
            timestamp=datetime.fromtimestamp(d["created_utc"], tz=timezone.utc),
            engagement=int(d.get("score", 0)) + int(d.get("num_comments", 0)),
            url=f"https://reddit.com{d.get('permalink', '')}",
        )

    def _new_pages(self, sub: str, headers: dict) -> Iterator[list[Post]]:
        after = None
        while True:
            params = {"limit": PAGE_LIMIT}
            if after:
                params["after"] = after
            resp = requests.get(
                f"{API}/r/{sub}/new",
                params=params,
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"  reddit r/{sub}/new: HTTP {resp.status_code}")
                return
            data = resp.json().get("data", {})
            yield [self._post(child["data"], sub) for child in data.get("children", [])]
            after = data.get("after")
            if not after:
                return

    def fetch(self) -> Iterable[Post]:
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "User-Agent": settings.reddit_user_agent,
        }
        for sub in settings.reddit_subreddits:
            yield from drain_pages(
                self._new_pages(sub, headers),
                lookback_hours=settings.ingest_lookback_hours,
                max_pages=MAX_NEW_PAGES,
                label=f"reddit r/{sub}/new",
            )
            resp = requests.get(
                f"{API}/r/{sub}/hot",
                params={"limit": 75},
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"  reddit r/{sub}/hot: HTTP {resp.status_code}")
                continue
            for child in resp.json().get("data", {}).get("children", []):
                yield self._post(child["data"], sub)
