"""Reddit adapter — official OAuth API (application-only grant), ToS-compliant.

Reads /new + /hot from the configured finance subreddits. Engagement is
score + comment count. Requires a free "script" app from
reddit.com/prefs/apps (client id + secret)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import requests

from worker.config import settings
from worker.ingest.base import Adapter
from worker.models import Post

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"


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

    def fetch(self) -> Iterable[Post]:
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "User-Agent": settings.reddit_user_agent,
        }
        for sub in settings.reddit_subreddits:
            for listing in ("new", "hot"):
                resp = requests.get(
                    f"{API}/r/{sub}/{listing}",
                    params={"limit": 75},
                    headers=headers,
                    timeout=30,
                )
                if resp.status_code != 200:
                    print(f"  reddit r/{sub}/{listing}: HTTP {resp.status_code}")
                    continue
                for child in resp.json().get("data", {}).get("children", []):
                    d = child["data"]
                    text = d.get("title", "")
                    body = (d.get("selftext") or "")[:1000]
                    if body and body not in ("[removed]", "[deleted]"):
                        text = f"{text}. {body}"
                    yield Post(
                        id=f"reddit:{d['id']}",
                        platform="reddit",
                        source=sub,
                        author=d.get("author", "unknown"),
                        text=text,
                        timestamp=datetime.fromtimestamp(d["created_utc"], tz=timezone.utc),
                        engagement=int(d.get("score", 0)) + int(d.get("num_comments", 0)),
                        url=f"https://reddit.com{d.get('permalink', '')}",
                    )
