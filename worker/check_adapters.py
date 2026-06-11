"""Smoke-test keyless adapters: python -m worker.check_adapters"""
from worker.ingest.edgar import EdgarAdapter
from worker.ingest.gdelt import GdeltAdapter
from worker.ingest.mastodon import MastodonAdapter
from worker.nlp.tickers import extract_tickers

for adapter in (EdgarAdapter(), GdeltAdapter(), MastodonAdapter()):
    posts = list(adapter.fetch())
    tagged = sum(1 for p in posts if extract_tickers(p.text))
    print(f"{adapter.name:10} posts={len(posts):4} with_tickers={tagged:4}")
    for p in posts[:2]:
        print(f"   [{p.source}] {p.text[:90]}".encode("ascii", "replace").decode())
