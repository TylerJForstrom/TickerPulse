"""StockTwits adapter — public JSON API, finance-native and pre-ticker-tagged.

Pulls the trending-symbols list, then each symbol's recent stream. The
public API is keyless but tightly rate-limited (~200 req/hr/IP), so the
symbol count is capped and errors degrade gracefully."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import requests

from worker.config import settings
from worker.ingest.base import Adapter
from worker.models import Post

API = "https://api.stocktwits.com/api/2"
HEADERS = {"User-Agent": "TickerPulse/1.0 (portfolio project)"}

# StockTwits' own bull/bear tags ride along as a prior; our model re-scores.
ST_SENTIMENT = {"Bullish": "bull", "Bearish": "bear"}


class StockTwitsAdapter(Adapter):
    name = "stocktwits"

    def available(self) -> bool:
        return True  # keyless public API

    def _trending_symbols(self) -> list[str]:
        resp = requests.get(f"{API}/trending/symbols.json", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return [s["symbol"] for s in resp.json().get("symbols", [])]

    def fetch(self) -> Iterable[Post]:
        try:
            symbols = self._trending_symbols()[: settings.stocktwits_max_symbols]
        except Exception as exc:
            print(f"  stocktwits trending failed: {exc}")
            return
        for sym in symbols:
            try:
                resp = requests.get(f"{API}/streams/symbol/{sym}.json",
                                    headers=HEADERS, timeout=30)
                if resp.status_code != 200:
                    continue
                for msg in resp.json().get("messages", []):
                    st_sent = ((msg.get("entities") or {}).get("sentiment") or {}).get("basic")
                    yield Post(
                        id=f"stocktwits:{msg['id']}",
                        platform="stocktwits",
                        source=sym,
                        author=(msg.get("user") or {}).get("username", "unknown"),
                        text=msg.get("body", ""),
                        timestamp=datetime.strptime(
                            msg["created_at"], "%Y-%m-%dT%H:%M:%SZ"
                        ).replace(tzinfo=timezone.utc),
                        engagement=int((msg.get("likes") or {}).get("total", 0)),
                        tickers=[s["symbol"] for s in msg.get("symbols", [])],
                        url=f"https://stocktwits.com/{(msg.get('user') or {}).get('username','')}/message/{msg['id']}",
                        sentiment=ST_SENTIMENT.get(st_sent),
                    )
            except Exception as exc:
                print(f"  stocktwits {sym} failed: {exc}")
