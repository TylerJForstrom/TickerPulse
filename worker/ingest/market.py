"""Real OHLCV market data per tracked ticker.

Primary source is yfinance (free, keyless). Crypto symbols map to their
Yahoo pairs (BTC → BTC-USD). If the network or Yahoo is unavailable —
offline demo regeneration, CI flakiness — a deterministic synthetic
random-walk fallback keeps the dashboard fully functional.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from worker.nlp.tickers import load_dictionary, ticker_sector

CRYPTO_SUFFIX = "-USD"


def yahoo_symbol(ticker: str) -> str:
    if ticker_sector(ticker) == "Crypto" and not ticker.endswith(CRYPTO_SUFFIX):
        tickers, _, _ = load_dictionary()
        # Stocks in the crypto sector (COIN, MSTR…) stay as-is; pure coins map.
        if ticker in {"BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "AVAX", "LINK", "SHIB", "PEPE"}:
            return f"{ticker}{CRYPTO_SUFFIX}"
    return ticker.replace(".", "-")  # BRK.B → BRK-B


def fetch_prices(tickers: list[str], days: int = 30, interval: str = "1h") -> dict[str, list[dict]]:
    """{ticker: [{ts, open, high, low, close, volume}]}. Best-effort per
    symbol; tickers that fail fall back to synthetic series."""
    out: dict[str, list[dict]] = {}
    try:
        import yfinance as yf

        for t in tickers:
            try:
                df = yf.Ticker(yahoo_symbol(t)).history(
                    period=f"{days}d", interval=interval, auto_adjust=True
                )
                if df is None or df.empty:
                    raise ValueError("empty frame")
                rows = []
                for ts, row in df.iterrows():
                    ts = ts.to_pydatetime()
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    rows.append({
                        "ts": ts.astimezone(timezone.utc).isoformat(),
                        "open": round(float(row["Open"]), 4),
                        "high": round(float(row["High"]), 4),
                        "low": round(float(row["Low"]), 4),
                        "close": round(float(row["Close"]), 4),
                        "volume": int(row["Volume"]),
                    })
                out[t] = rows
            except Exception as exc:
                print(f"yfinance failed for {t} ({exc}); using synthetic series")
                out[t] = synthetic_prices(t, days)
    except ImportError:
        print("yfinance not installed; using synthetic price series")
        for t in tickers:
            out[t] = synthetic_prices(t, days)
    return out


# Anchor prices so synthetic series look plausible per symbol.
ANCHORS = {
    "NVDA": 1250, "AAPL": 230, "MSFT": 470, "TSLA": 290, "GME": 28, "AMC": 5,
    "SPY": 600, "QQQ": 520, "BTC": 105000, "ETH": 5400, "COIN": 310,
    "MSTR": 420, "PLTR": 140, "SMCI": 45, "AMD": 175, "MRNA": 38, "LLY": 850,
    "GOOGL": 195, "AMZN": 220, "META": 700, "RKLB": 32, "BA": 185,
    "HOOD": 75, "SOFI": 14, "GLD": 280,
}


def synthetic_prices(ticker: str, days: int = 30) -> list[dict]:
    """Deterministic hourly random walk with mild drift — same seed per
    ticker so demo artifacts are reproducible."""
    rng = random.Random(hash(ticker) % (2**31))
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    n = days * 24
    price = float(ANCHORS.get(ticker, rng.uniform(20, 400)))
    drift = rng.uniform(-0.0001, 0.0004)
    rows = []
    for i in range(n):
        ts = now - timedelta(hours=n - 1 - i)
        ret = rng.gauss(drift, 0.006)
        o = price
        c = price * math.exp(ret)
        hi = max(o, c) * (1 + abs(rng.gauss(0, 0.002)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, 0.002)))
        rows.append({
            "ts": ts.isoformat(),
            "open": round(o, 4), "high": round(hi, 4),
            "low": round(lo, 4), "close": round(c, 4),
            "volume": int(abs(rng.gauss(1, 0.5)) * 2_000_000),
        })
        price = c
    return rows
