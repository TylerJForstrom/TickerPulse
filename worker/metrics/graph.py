"""Ticker relationship graph: which symbols travel together in the chatter.

Nodes are tickers (sized by mentions, colored by sector); edges are
co-mentions within a single post, weighted by count. The dashboard renders
this as the interactive node-link view."""

from __future__ import annotations

from collections import Counter
from itertools import combinations

from worker.models import Post
from worker.nlp.tickers import ticker_name, ticker_sector


def compute_graph(posts: list[Post], min_mentions: int = 5, min_edge: int = 2) -> dict:
    mentions = Counter(t for p in posts for t in p.tickers)
    keep = {t for t, n in mentions.items() if n >= min_mentions}

    edges = Counter()
    for p in posts:
        uniq = sorted({t for t in p.tickers if t in keep})
        for a, b in combinations(uniq, 2):
            edges[(a, b)] += 1

    connected = {t for pair, w in edges.items() if w >= min_edge for t in pair}
    nodes = [
        {
            "id": t,
            "name": ticker_name(t),
            "sector": ticker_sector(t),
            "mentions": mentions[t],
        }
        for t in sorted(keep & connected | {t for t in keep if mentions[t] >= min_mentions * 4})
    ]
    node_ids = {n["id"] for n in nodes}
    return {
        "nodes": nodes,
        "edges": [
            {"source": a, "target": b, "weight": w}
            for (a, b), w in edges.most_common(120)
            if w >= min_edge and a in node_ids and b in node_ids
        ],
    }
