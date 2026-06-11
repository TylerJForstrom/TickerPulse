"""Trend math: velocity, breakout, phases, ratios, windows, lead/lag."""

from datetime import datetime, timedelta, timezone

from worker.metrics.correlation import lead_lag
from worker.metrics.trends import (
    breakout_score, bull_bear_ratio, classify_phase, compute_ticker_trends,
    market_mood, velocity,
)
from worker.models import Post

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def make_post(i, hours_ago, ticker="NVDA", sentiment="bull", score=0.6, engagement=10):
    return Post(
        id=f"t:{i}", platform="sample", text=f"${ticker} test", author="a",
        timestamp=NOW - timedelta(hours=hours_ago), engagement=engagement,
        tickers=[ticker], sentiment=sentiment, sentiment_score=score,
    )


def test_velocity_sign_and_scale():
    assert velocity(48, 24, 24) == 1.0       # +1 mention/hour
    assert velocity(12, 36, 24) == -1.0
    assert velocity(10, 10, 24) == 0.0


def test_breakout_flat_baseline_no_spike():
    assert abs(breakout_score(1.0, [1.0] * 100)) < 0.1


def test_breakout_spike_is_large_and_capped():
    z = breakout_score(10.0, [1.0, 1.2, 0.8, 1.1, 0.9] * 20)
    assert z > 2.5
    assert breakout_score(1e9, [1.0] * 50) <= 10.0


def test_breakout_empty_baseline():
    assert breakout_score(5.0, []) == 0.0


def test_phase_classification():
    assert classify_phase(breakout=2.0, vel=0.5, prev_rate=0.1, baseline_mean=1.0) == "emerging"
    assert classify_phase(2.0, -0.5, 3.0, 1.0) == "peaking"
    assert classify_phase(0.5, -0.5, 3.0, 1.0) == "fading"
    assert classify_phase(0.2, 0.0, 1.0, 1.0) == "steady"


def test_bull_bear_ratio_smoothing():
    assert bull_bear_ratio(0, 0) == 1.0
    assert bull_bear_ratio(9, 0) == 10.0       # no division blow-ups
    assert bull_bear_ratio(3, 7) == 0.5


def test_compute_trends_emerging_spike():
    posts = []
    # quiet baseline: 1 mention every 4h, strictly before the 24h window
    posts += [make_post(f"b{i}", 25 + i * 4) for i in range(36)]
    # spike: 40 mentions in the last 12h
    posts += [make_post(f"s{i}", i * 0.3) for i in range(40)]
    trends = compute_ticker_trends(posts, window_hours=24, now=NOW)
    m = trends["NVDA"]
    assert m["mentions"] == 40
    assert m["phase"] == "emerging"
    assert m["breakout_score"] > 1.5
    assert m["velocity"] > 0
    assert len(m["sparkline"]) == 24
    assert m["share_of_voice"] == 1.0  # only ticker in play


def test_compute_trends_respects_min_mentions():
    posts = [make_post(i, 1, ticker="OBSCURE") for i in range(2)]
    assert "OBSCURE" not in compute_ticker_trends(posts, window_hours=24, now=NOW)


def test_market_mood_bullish_tilt():
    posts = [make_post(i, 1, sentiment="bull", score=0.8) for i in range(20)]
    posts += [make_post(f"x{i}", 1, sentiment="bear", score=-0.5) for i in range(5)]
    mood = market_mood(posts, window_hours=24, now=NOW)
    assert mood["index"] > 60
    assert mood["bull"] == 20 and mood["bear"] == 5


def test_lead_lag_detects_buzz_leading():
    # Irregularly spaced mention pulses whose |return| echo arrives 3h later —
    # non-periodic so the +3h lead can't alias onto a negative lag.
    pulse_hours = {7, 23, 41, 58, 80}
    rows = []
    for i in range(96):
        pulse = 30 if i in pulse_hours else 1
        move = 0.05 if (i - 3) in pulse_hours else 0.001
        rows.append({"mentions": pulse, "abs_return": move})
    ll = lead_lag(rows)
    assert ll["best_lag_hours"] == 3
    assert ll["best_lag_r"] > 0.5
