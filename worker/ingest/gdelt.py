"""GDELT adapter — the open global news index, keyless.

GDELT monitors worldwide news in real time and exposes a free full-text
search API (DOC 2.0). We pull English articles for a few finance queries;
headlines carry tickers/companies for the extractor."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Iterable

import requests

from worker.ingest.base import Adapter
from worker.models import Post

API = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERIES = [
    '"stock market" sourcelang:eng',
    '"earnings report" sourcelang:eng',
    '"federal reserve" sourcelang:eng',
    'bitcoin price sourcelang:eng',
]
HEADERS = {"User-Agent": "TickerPulse/1.0 (research project)"}


def _parse_seendate(s: str) -> datetime:
    # "20260611T143000Z"
    return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


class GdeltAdapter(Adapter):
    name = "gdelt"

    def available(self) -> bool:
        return True

    def fetch(self) -> Iterable[Post]:
        import time

        seen: set[str] = set()
        for i, q in enumerate(QUERIES):
            if i:
                time.sleep(8)  # GDELT free tier ~1 request / 5s per IP; be generous
            try:
                resp = requests.get(API, params={
                    "query": q, "mode": "artlist", "format": "json",
                    "maxrecords": 40, "timespan": "1d", "sort": "datedesc",
                }, headers=HEADERS, timeout=30)
                if resp.status_code != 200:
                    print(f"  gdelt '{q[:20]}': HTTP {resp.status_code}")
                    continue
                for art in resp.json().get("articles", []):
                    url = art.get("url", "")
                    title = art.get("title", "")
                    if not title or url in seen:
                        continue
                    seen.add(url)
                    uid = hashlib.sha1(url.encode()).hexdigest()[:16]
                    try:
                        ts = _parse_seendate(art["seendate"])
                    except (KeyError, ValueError):
                        ts = datetime.now(timezone.utc)
                    yield Post(
                        id=f"gdelt:{uid}",
                        platform="gdelt",
                        source=art.get("domain", "gdelt"),
                        author=art.get("domain", "unknown"),
                        text=title,
                        timestamp=ts,
                        engagement=0,
                        url=url,
                        lang="en",
                    )
            except Exception as exc:
                print(f"  gdelt '{q[:20]}' failed: {exc}")
