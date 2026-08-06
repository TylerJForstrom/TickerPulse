"""Quick RSS feed health check: python -m worker.check_feeds"""

import feedparser

from worker.ingest.rss import FEEDS

for name, url in FEEDS.items():
    try:
        feed = feedparser.parse(url)
        status = getattr(feed, "status", "?")
        print(f"{name:20} status={status} entries={len(feed.entries)}")
    except Exception as exc:
        print(f"{name:20} FAILED: {exc}")
