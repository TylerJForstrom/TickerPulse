"""Social-buzz vs price-move correlation — the flagship readout.

For each ticker we align hourly mention counts with hourly absolute returns
and volume, compute Pearson r at lags from -12h to +12h, and report the
best lag: positive lag = buzz LEADS price moves (chatter spikes before the
move), negative = buzz LAGS (people react after the candle). The dashboard
renders the aligned series plus a one-line human readout.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

MAX_LAG_HOURS = 12


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 8:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return 0.0
    return cov / math.sqrt(vx * vy)


def _hour_key(iso: str) -> str:
    return iso[:13]  # "2026-06-11T14"


def align_series(buckets: list[dict], prices: list[dict]) -> list[dict]:
    """Join mention buckets and OHLCV on the hour. Returns rows that have
    both a price candle and a (possibly zero) mention count. Candles outside
    the bucket coverage window are dropped — correlating real returns against
    hours where we simply have no social data yet would dilute r toward 0."""
    mentions = {_hour_key(b["bucket_start"]): b for b in buckets}
    if buckets:
        lo, hi = _hour_key(buckets[0]["bucket_start"]), _hour_key(buckets[-1]["bucket_start"])
        prices = [c for c in prices if lo <= _hour_key(c["ts"]) <= hi]
    rows = []
    for candle in prices:
        key = _hour_key(candle["ts"])
        b = mentions.get(key)
        prev_close = rows[-1]["close"] if rows else candle["open"]
        ret = (candle["close"] - prev_close) / prev_close if prev_close else 0.0
        rows.append({
            "ts": candle["ts"],
            "close": candle["close"],
            "volume": candle["volume"],
            "return": round(ret, 6),
            "abs_return": round(abs(ret), 6),
            "mentions": b["mentions"] if b else 0,
            "sentiment_avg": (b or {}).get("sentiment_avg"),
        })
    return rows


def lead_lag(rows: list[dict]) -> dict:
    """Correlate mentions vs |returns| across lags. lag>0: mentions shifted
    earlier (buzz leads); lag<0: buzz lags."""
    mentions = [float(r["mentions"]) for r in rows]
    moves = [r["abs_return"] for r in rows]
    if len(rows) < 24 or sum(mentions) == 0:
        return {"pearson_r": 0.0, "best_lag_hours": 0, "best_lag_r": 0.0, "by_lag": {}}
    by_lag: dict[int, float] = {}
    for lag in range(-MAX_LAG_HOURS, MAX_LAG_HOURS + 1):
        if lag >= 0:
            m, v = mentions[: len(mentions) - lag or None], moves[lag:]
        else:
            m, v = mentions[-lag:], moves[: len(moves) + lag]
        by_lag[lag] = round(_pearson(m, v), 4)
    # Best lag by correlation; near-ties resolve to the smallest |lag| so a
    # periodic signal doesn't alias a +3h lead into a -9h lag.
    best_lag = 0
    for lag in sorted(by_lag, key=abs):
        if by_lag[lag] > by_lag[best_lag] + 0.02:
            best_lag = lag
    return {
        "pearson_r": by_lag.get(0, 0.0),
        "best_lag_hours": best_lag,
        "best_lag_r": by_lag[best_lag],
        "by_lag": {str(k): v for k, v in by_lag.items()},
    }


def readout(ticker: str, ll: dict) -> str:
    r, lag, lag_r = ll["pearson_r"], ll["best_lag_hours"], ll["best_lag_r"]
    if abs(lag_r) < 0.15:
        return f"No meaningful buzz-move relationship for {ticker} in this window."
    strength = "strong" if abs(lag_r) >= 0.5 else "moderate" if abs(lag_r) >= 0.3 else "weak"
    if lag > 0:
        return (f"Chatter tends to LEAD price moves by ~{lag}h "
                f"({strength}, r={lag_r:.2f}) — social buzz has been an early signal for {ticker}.")
    if lag < 0:
        return (f"Chatter tends to FOLLOW price moves by ~{-lag}h "
                f"({strength}, r={lag_r:.2f}) — the crowd is reacting to {ticker}'s tape, not predicting it.")
    return f"Buzz and price moves are concurrent for {ticker} ({strength}, r={r:.2f})."


def compute_correlation(ticker: str, buckets: list[dict], prices: list[dict]) -> dict:
    rows = align_series(buckets, prices)
    ll = lead_lag(rows)
    return {
        "ticker": ticker,
        **ll,
        "readout": readout(ticker, ll),
        "series": rows[-7 * 24:],  # trailing week for the overlay chart
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
