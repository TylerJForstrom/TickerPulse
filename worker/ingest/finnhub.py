"""Finnhub adapter — market + crypto news via free API key (optional).

Activates when FINNHUB_API_KEY is set (free tier: 60 calls/min; we make 2
per run). https://finnhub.io/register"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import requests

from worker.config import settings
from worker.ingest.base import Adapter
from worker.models import Post

API = "https://finnhub.io/api/v1/news"
CATEGORIES = ["general", "crypto"]


class FinnhubAdapter(Adapter):
    name = "finnhub"

    def available(self) -> bool:
        return bool(settings.finnhub_api_key)

    def fetch(self) -> Iterable[Post]:
        for category in CATEGORIES:
            try:
                resp = requests.get(API, params={
                    "category": category, "token": settings.finnhub_api_key,
                }, timeout=30)
                if resp.status_code != 200:
                    print(f"  finnhub {category}: HTTP {resp.status_code}")
                    continue
                for item in resp.json()[:60]:
                    headline = item.get("headline", "")
                    if not headline:
                        continue
                    summary = (item.get("summary") or "")[:300]
                    yield Post(
                        id=f"finnhub:{item.get('id')}",
                        platform="finnhub",
                        source=item.get("source", category),
                        author=item.get("source", "finnhub"),
                        text=headline + (f". {summary}" if summary else ""),
                        timestamp=datetime.fromtimestamp(
                            item.get("datetime", 0), tz=timezone.utc
                        ),
                        engagement=0,
                        url=item.get("url", ""),
                    )
            except Exception as exc:
                print(f"  finnhub {category} failed: {exc}")
