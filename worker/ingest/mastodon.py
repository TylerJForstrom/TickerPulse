"""Mastodon adapter — public hashtag timelines, keyless.

Public timelines on the flagship instance are readable without auth.
Finance volume is modest but it widens the social diffusion picture."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

import requests

from worker.ingest.base import Adapter
from worker.models import Post

INSTANCE = "https://mastodon.social"
TAGS = ["stocks", "stockmarket", "investing", "bitcoin", "crypto"]
HEADERS = {"User-Agent": "TickerPulse/1.0 (research project)"}
TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", html)).strip()


class MastodonAdapter(Adapter):
    name = "mastodon"

    def available(self) -> bool:
        return True

    def fetch(self) -> Iterable[Post]:
        seen: set[str] = set()
        for tag in TAGS:
            try:
                resp = requests.get(
                    f"{INSTANCE}/api/v1/timelines/tag/{tag}",
                    params={"limit": 40}, headers=HEADERS, timeout=30,
                )
                if resp.status_code != 200:
                    print(f"  mastodon #{tag}: HTTP {resp.status_code}")
                    continue
                for status in resp.json():
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
                        timestamp=datetime.fromisoformat(
                            status["created_at"].replace("Z", "+00:00")
                        ),
                        engagement=int(status.get("favourites_count", 0))
                        + int(status.get("reblogs_count", 0)) * 2,
                        url=status.get("url", ""),
                        lang=lang,
                    )
            except Exception as exc:
                print(f"  mastodon #{tag} failed: {exc}")
