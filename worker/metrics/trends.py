"""Trend metrics per ticker, computed from normalized + scored posts.

Definitions (all windows in hours, all rates in mentions/hour):
- velocity        Δ rate between the current window and the previous one.
- breakout_score  z-score of the *recent* rate (last SPIKE_HOURS) against a
                  trailing baseline (history before the current window), so
                  a fresh spike isn't averaged away by a quiet morning. >2 ≈ unusual.
- phase           emerging | peaking | fading | steady, from breakout ×
                  velocity × whether the previous window was already hot.
- engagement_weighted_score   Σ log1p(engagement) over the window — a noisy
                  upvote on one post shouldn't outweigh ten real posts.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from worker.models import Post
from worker.nlp.tickers import ticker_name, ticker_sector

EPS = 1e-9
SPIKE_HOURS = 6  # recency window for breakout detection


def hourly_counts(posts: list[Post], ticker: str, now: datetime, hours: int) -> list[int]:
    """Mentions per hour for the trailing `hours`, oldest first."""
    counts = [0] * hours
    start = now - timedelta(hours=hours)
    for p in posts:
        if ticker in p.tickers and p.timestamp >= start:
            idx = min(hours - 1, int((p.timestamp - start).total_seconds() // 3600))
            counts[idx] += 1
    return counts


def velocity(curr_mentions: int, prev_mentions: int, window_hours: int) -> float:
    """Change in mentions/hour between consecutive windows."""
    return (curr_mentions - prev_mentions) / max(1, window_hours)


def breakout_score(current_rate: float, baseline_rates: list[float]) -> float:
    """Z-score of the current hourly rate vs a trailing per-hour baseline.
    Robust to short history; capped so one wild hour can't blow up the UI."""
    if not baseline_rates:
        return 0.0
    mean = sum(baseline_rates) / len(baseline_rates)
    var = sum((r - mean) ** 2 for r in baseline_rates) / len(baseline_rates)
    std = math.sqrt(var)
    z = (current_rate - mean) / (std + max(0.2, mean * 0.15) + EPS)
    return max(-10.0, min(10.0, z))


def classify_phase(breakout: float, vel: float, prev_rate: float, baseline_mean: float) -> str:
    hot = breakout >= 1.5
    was_hot = prev_rate > baseline_mean * 1.5 + EPS
    if hot and vel > 0:
        return "emerging"
    if hot:
        return "peaking"
    if was_hot and vel < 0:
        return "fading"
    return "steady"


def bull_bear_ratio(bull: int, bear: int) -> float:
    """Laplace-smoothed so 5:0 doesn't read as infinity."""
    return (bull + 1) / (bear + 1)


def compute_ticker_trends(
    posts: list[Post],
    window_hours: int = 24,
    now: datetime | None = None,
    history_hours: int = 168,
    min_mentions: int = 3,
) -> dict:
    """Returns {ticker: metrics dict} for tickers above the mention floor."""
    now = now or datetime.now(timezone.utc)
    win_start = now - timedelta(hours=window_hours)
    prev_start = now - timedelta(hours=2 * window_hours)

    by_ticker: dict[str, list[Post]] = defaultdict(list)
    for p in posts:
        for t in p.tickers:
            by_ticker[t].append(p)

    total_window_mentions = sum(
        1 for p in posts for t in p.tickers if p.timestamp >= win_start
    )

    out: dict[str, dict] = {}
    for ticker, tposts in by_ticker.items():
        window = [p for p in tposts if p.timestamp >= win_start]
        if len(window) < min_mentions:
            continue
        prev = [p for p in tposts if prev_start <= p.timestamp < win_start]

        counts = hourly_counts(posts, ticker, now, history_hours)
        baseline = [float(c) for c in counts[: history_hours - window_hours]]
        spike_start = now - timedelta(hours=SPIKE_HOURS)
        recent_rate = sum(1 for p in window if p.timestamp >= spike_start) / SPIKE_HOURS
        prev_rate = len(prev) / window_hours
        baseline_mean = sum(baseline) / len(baseline) if baseline else 0.0

        # Hour-of-day-matched baseline: compare the recent hours against the
        # *same clock hours* on prior days, so overnight lulls and market-hours
        # rushes don't masquerade as breakouts (or hide real ones).
        hist_start = now - timedelta(hours=history_hours)
        recent_hods = {(now - timedelta(hours=k + 1)).hour for k in range(SPIKE_HOURS)}
        matched = [
            float(c) for i, c in enumerate(counts[: history_hours - window_hours])
            if (hist_start + timedelta(hours=i)).hour in recent_hods
        ]

        vel = velocity(len(window), len(prev), window_hours)
        brk = breakout_score(recent_rate, matched or baseline)
        phase = classify_phase(brk, vel, prev_rate, baseline_mean)

        sentiments = Counter(p.sentiment for p in window if p.sentiment)
        bull, bear, neutral = sentiments["bull"], sentiments["bear"], sentiments["neutral"]
        scored = [p.sentiment_score for p in window if p.sentiment_score is not None]
        sent_avg = sum(scored) / len(scored) if scored else 0.0

        platforms = Counter(p.platform for p in window)
        origin = min(window, key=lambda p: p.timestamp).platform if window else None

        top_posts = sorted(window, key=lambda p: -p.engagement)[:5]

        out[ticker] = {
            "ticker": ticker,
            "name": ticker_name(ticker),
            "sector": ticker_sector(ticker),
            "window_hours": window_hours,
            "mentions": len(window),
            "mentions_prev": len(prev),
            "velocity": round(vel, 4),
            "breakout_score": round(brk, 3),
            "phase": phase,
            "share_of_voice": round(len(window) / (total_window_mentions + EPS), 5),
            "sentiment_avg": round(sent_avg, 4),
            "bull": bull,
            "bear": bear,
            "neutral": neutral,
            "bull_bear_ratio": round(bull_bear_ratio(bull, bear), 3),
            "engagement": sum(p.engagement for p in window),
            "engagement_weighted_score": round(
                sum(math.log1p(p.engagement) for p in window), 2
            ),
            "platforms": dict(platforms),
            "origin_platform": origin,
            "top_posts": [
                {
                    "id": p.id, "text": p.text, "author": p.author,
                    "platform": p.platform, "source": p.source,
                    "engagement": p.engagement, "url": p.url,
                    "sentiment": p.sentiment, "timestamp": p.timestamp.isoformat(),
                }
                for p in top_posts
            ],
            "sparkline": counts[-window_hours:],
        }
    return out


def bucket_series(
    posts: list[Post],
    ticker: str,
    bucket_minutes: int = 60,
    history_hours: int = 168,
    now: datetime | None = None,
) -> list[dict]:
    """Full time-series for a ticker: mentions, engagement, sentiment mix per
    bucket — feeds the detail-page charts and the DB ticker_buckets table."""
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(hours=history_hours)
    n_buckets = int(history_hours * 60 // bucket_minutes)
    buckets = [
        {
            "bucket_start": (start + timedelta(minutes=i * bucket_minutes)).isoformat(),
            "mentions": 0, "engagement": 0,
            "bull": 0, "bear": 0, "neutral": 0,
            "sentiment_sum": 0.0, "scored": 0,
            "platforms": Counter(),
        }
        for i in range(n_buckets)
    ]
    for p in posts:
        if ticker not in p.tickers or p.timestamp < start:
            continue
        idx = min(n_buckets - 1, int((p.timestamp - start).total_seconds() // (bucket_minutes * 60)))
        b = buckets[idx]
        b["mentions"] += 1
        b["engagement"] += p.engagement
        if p.sentiment in ("bull", "bear", "neutral"):
            b[p.sentiment] += 1
        if p.sentiment_score is not None:
            b["sentiment_sum"] += p.sentiment_score
            b["scored"] += 1
        b["platforms"][p.platform] += 1

    out = []
    for b in buckets:
        out.append({
            "bucket_start": b["bucket_start"],
            "mentions": b["mentions"],
            "engagement": b["engagement"],
            "bull": b["bull"], "bear": b["bear"], "neutral": b["neutral"],
            "sentiment_avg": round(b["sentiment_sum"] / b["scored"], 4) if b["scored"] else None,
            "platforms": dict(b["platforms"]),
        })
    return out


def market_mood(posts: list[Post], window_hours: int = 24, now: datetime | None = None) -> dict:
    """Engagement-weighted bull/bear index across all chatter, 0–100."""
    now = now or datetime.now(timezone.utc)
    win_start = now - timedelta(hours=window_hours)
    window = [p for p in posts if p.timestamp >= win_start and p.sentiment_score is not None]
    if not window:
        return {"index": 50.0, "label": "neutral", "bull": 0, "bear": 0, "neutral": 0, "posts": 0}
    wsum = sum(math.log1p(p.engagement) + 1.0 for p in window)
    weighted = sum((math.log1p(p.engagement) + 1.0) * p.sentiment_score for p in window) / wsum
    index = round((weighted + 1) / 2 * 100, 1)
    label = ("extreme greed" if index >= 75 else "greed" if index >= 60 else
             "neutral" if index > 40 else "fear" if index > 25 else "extreme fear")
    sentiments = Counter(p.sentiment for p in window)
    return {
        "index": index,
        "label": label,
        "bull": sentiments["bull"],
        "bear": sentiments["bear"],
        "neutral": sentiments["neutral"],
        "posts": len(window),
    }
