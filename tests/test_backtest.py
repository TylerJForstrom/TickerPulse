"""Flag-replay backtest: event detection, forward returns, summary math."""

from datetime import datetime, timedelta, timezone

from worker.metrics.backtest import (
    _close_at, replay_flags, score_events, summarize,
)
from worker.models import Post

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def hourly_prices(start: datetime, hours: int, base: float, jump_at: int | None = None,
                  jump_pct: float = 0.05):
    rows, price = [], base
    for i in range(hours):
        if jump_at is not None and i == jump_at:
            price *= 1 + jump_pct
        rows.append({"ts": (start + timedelta(hours=i)).isoformat(),
                     "open": price, "high": price, "low": price,
                     "close": round(price, 4), "volume": 1000})
    return rows


def make_posts(ticker: str, spike_hours_ago: float, n_spike: int = 50, n_base: int = 40):
    posts = [
        Post(id=f"b{i}", platform="sample", text=f"${ticker}", author="a",
             timestamp=NOW - timedelta(hours=30 + i * 3.4), tickers=[ticker],
             sentiment="neutral", sentiment_score=0.0)
        for i in range(n_base)
    ]
    posts += [
        Post(id=f"s{i}", platform="sample", text=f"${ticker} squeeze", author="a",
             timestamp=NOW - timedelta(hours=spike_hours_ago + (i % 10) * 0.3),
             tickers=[ticker], sentiment="bull", sentiment_score=0.7)
        for i in range(n_spike)
    ]
    return posts


def test_replay_finds_the_spike_flag():
    events = replay_flags(make_posts("GME", spike_hours_ago=3), now=NOW)
    assert any(e["ticker"] == "GME" for e in events)


def test_replay_dedupes_one_event_per_flareup():
    events = replay_flags(make_posts("GME", spike_hours_ago=3), now=NOW)
    assert len([e for e in events if e["ticker"] == "GME"]) == 1


def test_close_at_respects_gap_tolerance():
    start = NOW - timedelta(hours=100)
    prices = hourly_prices(start, 50, 100.0)  # series ends 50h before NOW
    assert _close_at(prices, NOW) is None      # gap too large
    assert _close_at(prices, start + timedelta(hours=10)) == 100.0


def test_score_events_forward_returns():
    flagged = NOW - timedelta(hours=48)
    start = NOW - timedelta(hours=168)
    # price jumps +5% exactly 24h after the flag
    jump_idx = int((flagged - start).total_seconds() // 3600) + 24
    prices = {"GME": hourly_prices(start, 168, 100.0, jump_at=jump_idx)}
    events = [{"ticker": "GME", "flagged_at": flagged.isoformat()}]
    score_events(events, prices)
    assert events[0]["returns"]["4"] == 0.0
    assert abs(events[0]["returns"]["24"] - 5.0) < 0.2
    assert abs(events[0]["returns"]["48"] - 5.0) < 0.2


def test_score_events_unelapsed_horizon_is_none():
    flagged = NOW - timedelta(hours=2)
    start = NOW - timedelta(hours=168)
    prices = {"GME": hourly_prices(start, 168, 100.0)}
    events = [{"ticker": "GME", "flagged_at": flagged.isoformat()}]
    score_events(events, prices)
    assert events[0]["returns"]["48"] is None  # future not knowable


def test_summarize_win_rate_and_median():
    events = [
        {"returns": {"4": 1.0, "24": 2.0, "48": None}},
        {"returns": {"4": -1.0, "24": 4.0, "48": None}},
        {"returns": {"4": 3.0, "24": -2.0, "48": None}},
    ]
    s = summarize(events)
    assert s["events"] == 3
    assert s["horizons"]["4"]["n"] == 3
    assert abs(s["horizons"]["4"]["win_rate"] - 2 / 3) < 1e-3  # rounded to 3dp
    assert s["horizons"]["4"]["median"] == 1.0
    assert s["horizons"]["48"]["n"] == 0
    assert s["horizons"]["48"]["win_rate"] is None
