"""Flag replay backtest: did the 'emerging' flags actually precede moves?

Replays history in `step_hours` increments. At each as-of time the trend
engine runs exactly as it would have live (using only posts known by then);
every *emerging* flag above the breakout floor becomes an event, and each
event is scored by the ticker's forward return at several horizons using
the real price series.

This is deliberately honest: flags that fizzle count against the win rate.
The point is to answer "is social buzz a usable early signal?" with data
instead of vibes — the dashboard shows the result either way.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from worker.metrics.trends import compute_ticker_trends
from worker.models import Post

HORIZONS = (4, 24, 48)            # hours ahead to measure
BREAKOUT_FLOOR = 1.5              # flag quality bar for an event
MAX_CANDLE_GAP_H = 30.0           # tolerate weekends/closed market when
                                  # matching an as-of time to a candle


def _parse_ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _close_at(prices: list[dict], when: datetime, max_gap_h: float = MAX_CANDLE_GAP_H):
    """Close of the last candle at/before `when` (None if too far away)."""
    best = None
    for c in prices:
        ts = _parse_ts(c["ts"])
        if ts <= when:
            best = (ts, c["close"])
        else:
            break
    if best is None:
        return None
    if (when - best[0]).total_seconds() / 3600 > max_gap_h:
        return None
    return best[1]


def replay_flags(
    posts: list[Post],
    window_hours: int = 24,
    step_hours: int = 6,
    now: datetime | None = None,
    history_hours: int = 168,
) -> list[dict]:
    """Walk back through history flagging emerging tickers as-of each step."""
    now = now or datetime.now(timezone.utc)
    events: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (ticker, day-bucket) — one event per flare-up
    # Oldest as-of needs at least one window of history before it.
    n_steps = max(0, (history_hours - window_hours) // step_hours)
    for k in range(n_steps, -1, -1):
        as_of = now - timedelta(hours=k * step_hours)
        visible = [p for p in posts if p.timestamp <= as_of]
        if len(visible) < 50:
            continue
        trends = compute_ticker_trends(
            visible, window_hours=window_hours, now=as_of, history_hours=history_hours
        )
        for ticker, m in trends.items():
            if m["phase"] != "emerging" or m["breakout_score"] < BREAKOUT_FLOOR:
                continue
            # Dedupe: the same flare-up re-flags at consecutive steps; keep the
            # first sighting per ticker per ~day.
            day_key = (as_of - timedelta(hours=0)).strftime("%Y-%m-%d")
            recent = any(
                e["ticker"] == ticker
                and abs((_parse_ts(e["flagged_at"]) - as_of).total_seconds()) < 24 * 3600
                for e in events
            )
            if recent or (ticker, day_key) in seen:
                continue
            seen.add((ticker, day_key))
            events.append({
                "ticker": ticker,
                "name": m["name"],
                "flagged_at": as_of.isoformat(),
                "breakout_score": m["breakout_score"],
                "mentions": m["mentions"],
                "sentiment_avg": m["sentiment_avg"],
                "bull_bear_ratio": m["bull_bear_ratio"],
            })
    return events


def score_events(events: list[dict], prices_by_ticker: dict[str, list[dict]],
                 horizons: tuple[int, ...] = HORIZONS) -> None:
    """Attach forward returns (in %) per horizon; None when prices missing
    or the horizon hasn't elapsed yet."""
    for e in events:
        prices = prices_by_ticker.get(e["ticker"]) or []
        t0 = _parse_ts(e["flagged_at"])
        base = _close_at(prices, t0)
        e["returns"] = {}
        for h in horizons:
            ret = None
            if base:
                target = t0 + timedelta(hours=h)
                last_ts = _parse_ts(prices[-1]["ts"]) if prices else None
                if last_ts and last_ts >= target - timedelta(hours=MAX_CANDLE_GAP_H / 2):
                    fwd = _close_at(prices, target)
                    if fwd is not None:
                        ret = round((fwd / base - 1) * 100, 3)
            e["returns"][str(h)] = ret


def summarize(events: list[dict], horizons: tuple[int, ...] = HORIZONS) -> dict:
    summary = {"events": len(events), "horizons": {}}
    for h in horizons:
        rets = [e["returns"][str(h)] for e in events if e["returns"].get(str(h)) is not None]
        # Exactly-zero returns are market-closed artifacts (the close was
        # carried forward over a shut session), not real outcomes — exclude
        # them from the win rate instead of counting them as losses.
        moved = [r for r in rets if abs(r) > 1e-9]
        if not rets:
            summary["horizons"][str(h)] = {"n": 0, "flat": 0, "win_rate": None,
                                           "avg": None, "median": None}
            continue
        rets_sorted = sorted(rets)
        mid = len(rets_sorted) // 2
        median = (rets_sorted[mid] if len(rets_sorted) % 2
                  else (rets_sorted[mid - 1] + rets_sorted[mid]) / 2)
        summary["horizons"][str(h)] = {
            "n": len(rets),
            "flat": len(rets) - len(moved),
            "win_rate": round(sum(1 for r in moved if r > 0) / len(moved), 3) if moved else None,
            "avg": round(sum(rets) / len(rets), 3),
            "median": round(median, 3),
        }
    return summary


def run_backtest(posts: list[Post], prices_by_ticker: dict[str, list[dict]],
                 window_hours: int = 24, now: datetime | None = None) -> dict:
    events = replay_flags(posts, window_hours=window_hours, now=now)
    score_events(events, prices_by_ticker)
    events.sort(key=lambda e: e["flagged_at"], reverse=True)
    return {
        "summary": summarize(events),
        "events": events[:60],
        "params": {
            "window_hours": window_hours,
            "breakout_floor": BREAKOUT_FLOOR,
            "horizons": list(HORIZONS),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
