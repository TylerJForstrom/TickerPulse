"""Influence weighting: platform authority × engagement."""

from datetime import datetime, timezone

from worker.metrics.weights import post_weight, weighted_sentiment
from worker.models import Post

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def make(platform, engagement, score):
    return Post(id=f"{platform}:{engagement}:{score}", platform=platform, text="x",
                author="a", timestamp=NOW, engagement=engagement,
                sentiment_score=score)


def test_newsroom_headline_outweighs_quiet_micropost():
    assert post_weight(make("rss", 0, 0)) > post_weight(make("bluesky", 0, 0))


def test_engagement_grows_weight_sublinearly():
    w0 = post_weight(make("stocktwits", 0, 0))
    w100 = post_weight(make("stocktwits", 100, 0))
    w10k = post_weight(make("stocktwits", 10_000, 0))
    assert w0 < w100 < w10k
    # 100x the engagement must NOT mean 100x the influence
    assert w10k / w100 < 3


def test_weighted_sentiment_leans_toward_influence():
    posts = [
        make("rss", 50, 0.8),        # heavyweight bullish headline
        make("bluesky", 0, -0.8),    # featherweight bearish post
    ]
    s = weighted_sentiment(posts)
    assert s > 0.4  # far closer to the headline than the midpoint


def test_weighted_sentiment_uniform_inputs_unchanged():
    posts = [make("sample", 10, 0.5), make("sample", 10, -0.1)]
    assert abs(weighted_sentiment(posts) - 0.2) < 1e-9


def test_weighted_sentiment_empty():
    assert weighted_sentiment([]) is None
    assert weighted_sentiment([make("rss", 5, None)]) is None
