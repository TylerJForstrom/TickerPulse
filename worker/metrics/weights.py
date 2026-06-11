"""Post influence weighting.

Not every post moves the same number of eyeballs. A wire-service headline
syndicated across brokerages reaches a different audience than a zero-like
microblog post, and a 2,000-upvote thread is a conversation, not a remark.

    weight(post) = platform_authority × (1 + log1p(engagement))

`platform_authority` is a fixed per-platform multiplier — a coarse,
documented proxy for typical per-post audience. `log1p(engagement)` keeps
viral posts influential but sub-linear, so one meme can't outvote a broad
conversation. Weights apply to *sentiment aggregation* (per-ticker averages
and the market-mood index); raw mention counts stay honest and unweighted.
"""

from __future__ import annotations

import math

from worker.models import Post

# Coarse per-post audience proxies. Documented, debatable, and centralized
# here on purpose — tune with data, not vibes, as the corpus grows.
PLATFORM_AUTHORITY = {
    "sec": 3.0,         # primary-source corporate disclosures
    "rss": 2.5,         # institutional newsrooms, syndicated reach
    "finnhub": 2.2,     # curated market-news wire
    "gdelt": 2.0,       # global news index, mixed outlet quality
    "hackernews": 1.5,  # front-page posts reach a large, engaged audience
    "reddit": 1.3,      # big-sub threads, vote-gated visibility
    "stocktwits": 1.0,  # finance-native baseline
    "bluesky": 0.9,     # broad but low fan-out per post today
    "mastodon": 0.8,    # smallest typical reach in the mix
    "sample": 1.0,      # demo data: neutral
}


def post_weight(post: Post) -> float:
    authority = PLATFORM_AUTHORITY.get(post.platform, 1.0)
    return authority * (1.0 + math.log1p(max(0, post.engagement)))


def weighted_sentiment(posts: list[Post]) -> float | None:
    """Influence-weighted average sentiment score, -1..+1."""
    pairs = [(post_weight(p), p.sentiment_score) for p in posts
             if p.sentiment_score is not None]
    if not pairs:
        return None
    total = sum(w for w, _ in pairs)
    return sum(w * s for w, s in pairs) / total if total else None
