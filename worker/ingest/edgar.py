"""SEC EDGAR adapter — live corporate filings, keyless and official.

Pulls the latest 8-K filings (material corporate events: M&A, guidance,
executive changes) and Form 4s (insider buys/sells) from EDGAR's public
"current events" Atom feed. Filing titles carry the company name, which the
ticker dictionary's alias matching maps to symbols.

SEC fair-access policy: declared User-Agent, max 10 req/s — we make 2
requests per run. https://www.sec.gov/os/accessing-edgar-data
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Iterable

import requests

from worker.ingest.base import Adapter
from worker.models import Post

FEED = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
        "&type={form}&company=&dateb=&owner=include&count=40&output=atom")
FORMS = {
    "8-K": "filed an 8-K (material corporate event)",
    "4": "reported an insider transaction (Form 4)",
}
# SEC requires a declared contact in the UA (https://www.sec.gov/os/accessing-edgar-data)
HEADERS = {"User-Agent": "TickerPulse research project tylerjamesforstrom@gmail.com"}


def _clean_title(title: str) -> str:
    # "8-K - NVIDIA CORP (0001045810) (Filer)" → "NVIDIA CORP"
    m = re.match(r"^[\w/-]+\s+-\s+(.+?)\s*\(\d{8,}\)", title)
    return m.group(1).strip() if m else title


class EdgarAdapter(Adapter):
    name = "sec"

    def available(self) -> bool:
        return True

    def fetch(self) -> Iterable[Post]:
        import feedparser

        for form, blurb in FORMS.items():
            try:
                resp = requests.get(FEED.format(form=form), headers=HEADERS, timeout=30)
                if resp.status_code != 200:
                    print(f"  edgar {form}: HTTP {resp.status_code}")
                    continue
                feed = feedparser.parse(resp.content)
                for entry in feed.entries:
                    title = entry.get("title", "")
                    if not title:
                        continue
                    company = _clean_title(title)
                    if entry.get("updated_parsed"):
                        from time import mktime
                        ts = datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
                    else:
                        ts = datetime.now(timezone.utc)
                    uid = hashlib.sha1((entry.get("id") or title).encode()).hexdigest()[:16]
                    yield Post(
                        id=f"sec:{uid}",
                        platform="sec",
                        source=f"edgar-{form.lower()}",
                        author="SEC EDGAR",
                        # Company name in the text lets alias matching tag the
                        # ticker; the blurb keeps it readable in Top Posts.
                        text=f"{company} {blurb}.",
                        timestamp=ts,
                        engagement=0,
                        url=entry.get("link", ""),
                    )
            except Exception as exc:
                print(f"  edgar {form} failed: {exc}")
