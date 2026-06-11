"""Finance news RSS adapter — headlines as low-engagement chatter context."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from time import mktime
from typing import Iterable

from worker.ingest.base import Adapter
from worker.models import Post

FEEDS = {
    "cnbc-markets": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "marketwatch-top": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "yahoo-finance": "https://finance.yahoo.com/news/rssindex",
}


class RSSAdapter(Adapter):
    name = "rss"

    def available(self) -> bool:
        try:
            import feedparser  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch(self) -> Iterable[Post]:
        import feedparser

        for source, url in FEEDS.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:40]:
                    title = entry.get("title", "")
                    if not title:
                        continue
                    if entry.get("published_parsed"):
                        ts = datetime.fromtimestamp(
                            mktime(entry.published_parsed), tz=timezone.utc
                        )
                    else:
                        ts = datetime.now(timezone.utc)
                    uid = hashlib.sha1(
                        (entry.get("id") or entry.get("link") or title).encode()
                    ).hexdigest()[:16]
                    yield Post(
                        id=f"rss:{uid}",
                        platform="rss",
                        source=source,
                        author=source,
                        text=title + (". " + entry.get("summary", "")[:300]
                                      if entry.get("summary") else ""),
                        timestamp=ts,
                        engagement=0,
                        url=entry.get("link", ""),
                    )
            except Exception as exc:
                print(f"  rss {source} failed: {exc}")
