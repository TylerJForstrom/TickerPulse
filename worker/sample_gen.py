"""Synthetic-but-realistic sample dataset generator (demo mode).

Produces `worker/data/sample_posts.json`: ~5k finance social posts over the
trailing 7 days with deliberate narrative arcs (an earnings breakout, a
fading controversy, a fresh squeeze, steady mega-cap baseline, macro/Fed
chatter…) so every downstream metric — velocity, breakout, bull:bear,
diffusion, topic clusters — has real structure to find.

Timestamps are generated relative to *now*, so regenerating right before a
deploy makes the demo look current. Deterministic under --seed.

Usage:  python -m worker.sample_gen [--posts 5000] [--seed 42] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT_DEFAULT = Path(__file__).parent / "data" / "sample_posts.json"
HOURS = 168  # 7 days

# ── voice banks ──────────────────────────────────────────────────────────

BULL = [
    "{sym} absolutely ripping today. Volume is insane, this has legs.",
    "Loaded up on more {sym} this morning. The thesis keeps getting stronger.",
    "{sym} breaking out of the range on huge volume. Next leg up starting.",
    "{name} guidance was a beat across the board. {sym} to new highs.",
    "Been holding {sym} since last year, finally paying off. Not selling a share.",
    "{sym} calls printing. Told you all last week this was coming.",
    "The dip on {sym} was a gift. Institutions are accumulating, watch the tape.",
    "{name} is executing flawlessly. {sym} is still cheap at these levels imo.",
    "{sym} short interest is fuel. This goes higher.",
    "Strong hands on {sym}. Every dip gets bought within minutes.",
    "{sym} just reclaimed the 50dma with conviction. Bullish continuation setup.",
    "Adding {sym} to the long-term portfolio. Best risk/reward on the board.",
]

BEAR = [
    "{sym} looks exhausted here. Taking profits before this rolls over.",
    "The {name} numbers don't add up. {sym} is priced for perfection.",
    "{sym} breaking down below support on rising volume. Not good.",
    "Puts on {sym}. This valuation makes zero sense in this rate environment.",
    "Everyone is euphoric on {sym} which is exactly when you should worry.",
    "{name} margins are getting crushed and nobody is talking about it. {sym}",
    "{sym} insiders dumping shares all month. Follow the money.",
    "Sold all my {sym} today. The momentum is gone and guidance was weak.",
    "{sym} is a bagholder factory at this price. Wait for the flush.",
    "Bear flag forming on {sym} daily. Target is the gap below.",
]

NEUTRAL = [
    "What's everyone's price target on {sym} after this move?",
    "Is {sym} a buy here or wait for a pullback? Genuinely torn.",
    "Interesting volume profile on {sym} today. Watching closely.",
    "Anyone have a good breakdown of the {name} earnings call?",
    "{sym} options chain is pricing a big move either way this week.",
    "Adding {sym} to the watchlist. Curious what the smart money thinks.",
    "How does {name} compare to its competitors at current multiples? {sym}",
    "{sym} IV is elevated going into the print. Could go either way.",
]

# Theme-specific vocabulary so clustering has distinct lexical islands.
THEME_TEMPLATES = {
    "earnings": [
        "Earnings szn: {sym} reports after the close. Whisper numbers are wild.",
        "{name} beat on revenue and raised full-year guidance. {sym} gapping up.",
        "That {sym} earnings call was something. Margin commentary was the headline.",
        "EPS beat, revenue beat, guide raised — {sym} did everything right.",
    ],
    "fed": [
        "CPI print tomorrow. If it comes in hot, {sym} is in trouble.",
        "Powell speaks at 2pm. Rate cut odds repricing fast, watch {sym}.",
        "The Fed is boxed in. Sticky inflation vs slowing jobs. {sym} chop continues.",
        "10-year yield ripping again. Growth names like {sym} hate this.",
        "Rate cut hopium is back. {sym} squeezing on the dovish minutes.",
    ],
    "ai": [
        "AI capex is still accelerating. {sym} is the purest picks-and-shovels play.",
        "Every hyperscaler raised AI spend guidance. Demand for {sym} compute is bottomless.",
        "The AI trade isn't over, it's broadening. {sym} next in line.",
        "Datacenter buildout numbers are staggering. {sym} backlog at record highs.",
        "Inference demand is the story now, not training. {sym} positioned perfectly.",
    ],
    "squeeze": [
        "{sym} short interest at 30%+ and the borrow rate is exploding. You know what comes next.",
        "Gamma ramp loading on {sym}. Market makers are trapped.",
        "{sym} squeeze thesis: high SI, low float, catalysts this week. Strap in.",
        "The shorts never covered {sym}. FTDs piling up. Tick tock.",
        "{sym} halted twice already today. Squeeze is on.",
    ],
    "crypto": [
        "{name} breaking out while equities chop. The decoupling is real. {sym}",
        "ETF inflows for {sym} hit a record this week. Institutions are here.",
        "{sym} on-chain activity at yearly highs. Accumulation phase over.",
        "Halving supply shock thesis playing out for {sym}. Up only.",
        "Altseason loading. {sym} leading the charge off the bottom.",
    ],
    "evs": [
        "EV demand is softening and {sym} keeps cutting prices. Margin death spiral?",
        "{name} deliveries missed estimates again. {sym} bulls in denial.",
        "Charging infra buildout is the quiet winner. {sym} exposure is underrated.",
    ],
    "pharma": [
        "{name} trial data underwhelmed. {sym} giving back the whole run-up.",
        "GLP-1 demand is rewriting the entire sector. {sym} capacity can't keep up.",
        "FDA decision on {sym} expected Friday. Binary event, size accordingly.",
    ],
    "defense": [
        "Defense budgets only go up from here. {sym} backlog tells the story.",
        "{name} just won another contract. {sym} quietly at all-time highs.",
        "Space launch cadence doubling yearly. {sym} is the pure play.",
    ],
}

MACRO_NOTICKER = [
    "Breadth is terrible. Five stocks are carrying the entire index again.",
    "VIX under 14 while the world burns. What could go wrong.",
    "Jobs number Friday. Positioning into it feels maximally crowded.",
    "This market only goes up on bad news now. Good news is bad news.",
    "Retail flows hit a record this week per the JPM desk note.",
    "Yield curve un-inverting is historically when things actually break.",
    "Everyone's bullish. Put/call at extremes. Contrarian alarm bells.",
    "Liquidity is thinning into the holiday. Expect weird tape.",
]

AUTHORS = [
    "DeepValueDegen", "thetagang_steve", "MacroMarx", "QuietCompounder",
    "VolHunterX", "dipbuyer2021", "OptionsOracle", "ChartWitch",
    "fundamental_frank", "moon_mission_cmdr", "BearishBeth", "IndexAndChill",
    "GammaGoblin", "SatoshiSon", "DivGrowthDan", "ruth_lessinvestor",
    "TendieTracker", "FOMOsapiens", "smallcap_sniper", "PermabullPete",
    "QuantJanitor", "drawdown_dave", "LadyLiquidity", "thesis_drift",
    "CashSecuredKev", "RiskParityRita", "AlphaSeeker88", "BondVigilante_",
]

SUBREDDITS = ["wallstreetbets", "stocks", "investing", "options", "CryptoCurrency"]


@dataclass
class Event:
    """A chatter spike: starts `hours_ago`, decays over `duration` hours."""
    hours_ago: float
    duration: float
    multiplier: float
    sentiment: tuple[float, float, float] | None = None  # bull, bear, neutral
    theme: str | None = None


@dataclass
class Narrative:
    ticker: str
    name: str
    base_rate: float                       # posts/hour baseline (all platforms)
    sentiment: tuple[float, float, float]  # bull, bear, neutral mix
    themes: list[str] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    platforms: dict[str, float] = field(
        default_factory=lambda: {"stocktwits": 0.45, "reddit": 0.38, "bluesky": 0.12, "hackernews": 0.05}
    )
    co_mentions: list[str] = field(default_factory=list)
    crypto: bool = False


NARRATIVES = [
    # Flagship arc: earnings blowout ~44h ago → huge breakout, still elevated.
    Narrative("NVDA", "NVIDIA", 4.0, (0.50, 0.18, 0.32), ["ai", "earnings"],
              [Event(44, 36, 7.0, (0.70, 0.10, 0.20), "earnings"),
               Event(20, 18, 3.5, (0.65, 0.12, 0.23), "ai")],
              co_mentions=["AMD", "SMCI", "TSM", "MSFT"]),
    # Fresh squeeze igniting *right now* → "emerging" flag + spike alert.
    Narrative("GME", "GameStop", 1.5, (0.55, 0.15, 0.30), ["squeeze"],
              [Event(5, 18, 14.0, (0.78, 0.08, 0.14), "squeeze")],
              co_mentions=["AMC"]),
    # Controversy peaked 4 days ago, now fading → bearish, "fading" phase.
    Narrative("TSLA", "Tesla", 3.5, (0.30, 0.45, 0.25), ["evs"],
              [Event(96, 60, 4.0, (0.18, 0.62, 0.20), "evs")],
              co_mentions=["RIVN", "NIO", "F"]),
    # Steady AI riser, bullish drift, modest event.
    Narrative("PLTR", "Palantir", 1.8, (0.58, 0.16, 0.26), ["ai"],
              [Event(30, 30, 2.2, theme="ai")], co_mentions=["NVDA", "MSFT"]),
    # Accounting drama → bearish spike 3 days ago.
    Narrative("SMCI", "Super Micro", 0.9, (0.25, 0.55, 0.20), ["ai"],
              [Event(70, 30, 5.0, (0.12, 0.72, 0.16))], co_mentions=["NVDA", "DELL"]),
    # Crypto rally: BTC leads, ETH/COIN follow.
    Narrative("BTC", "Bitcoin", 3.0, (0.58, 0.18, 0.24), ["crypto"],
              [Event(56, 48, 3.0, (0.68, 0.12, 0.20), "crypto")],
              co_mentions=["ETH", "COIN", "MSTR"], crypto=True),
    Narrative("ETH", "Ethereum", 1.6, (0.55, 0.18, 0.27), ["crypto"],
              [Event(48, 40, 2.5, theme="crypto")], co_mentions=["BTC", "SOL"], crypto=True),
    Narrative("COIN", "Coinbase", 1.0, (0.52, 0.22, 0.26), ["crypto"],
              [Event(50, 40, 2.4, theme="crypto")], co_mentions=["BTC", "MSTR", "HOOD"]),
    Narrative("MSTR", "MicroStrategy", 0.8, (0.50, 0.26, 0.24), ["crypto"],
              [Event(52, 40, 2.6, theme="crypto")], co_mentions=["BTC"]),
    # Bad trial data → bear spike fading.
    Narrative("MRNA", "Moderna", 0.5, (0.20, 0.58, 0.22), ["pharma"],
              [Event(80, 26, 4.5, (0.10, 0.74, 0.16), "pharma")], co_mentions=["PFE"]),
    # GLP-1 secular bull.
    Narrative("LLY", "Eli Lilly", 0.8, (0.60, 0.14, 0.26), ["pharma"],
              [Event(36, 30, 1.8, theme="pharma")], co_mentions=["NVO"]),
    # Mega-cap steady baseline.
    Narrative("AAPL", "Apple", 2.6, (0.40, 0.28, 0.32), ["earnings"]),
    Narrative("MSFT", "Microsoft", 2.2, (0.48, 0.20, 0.32), ["ai"], co_mentions=["NVDA"]),
    Narrative("AMZN", "Amazon", 1.6, (0.45, 0.24, 0.31), ["earnings"]),
    Narrative("META", "Meta Platforms", 1.5, (0.44, 0.26, 0.30), ["ai"]),
    Narrative("GOOGL", "Alphabet", 1.7, (0.42, 0.28, 0.30), ["ai"]),
    Narrative("AMD", "AMD", 1.4, (0.46, 0.26, 0.28), ["ai"],
              [Event(40, 30, 1.8, theme="ai")], co_mentions=["NVDA", "INTC"]),
    # Macro / index chatter around a CPI print ~28h ago.
    Narrative("SPY", "S&P 500 ETF", 2.8, (0.34, 0.36, 0.30), ["fed"],
              [Event(28, 20, 3.0, (0.30, 0.44, 0.26), "fed")], co_mentions=["QQQ", "IWM"]),
    Narrative("QQQ", "Nasdaq 100 ETF", 1.8, (0.36, 0.34, 0.30), ["fed"],
              [Event(28, 20, 2.6, theme="fed")], co_mentions=["SPY"]),
    # Defense / space steady.
    Narrative("RKLB", "Rocket Lab", 0.7, (0.56, 0.16, 0.28), ["defense"],
              [Event(60, 36, 1.7, theme="defense")], co_mentions=["LMT", "BA"]),
    Narrative("BA", "Boeing", 0.9, (0.26, 0.48, 0.26), ["defense"]),
    # Fintech mid-tier.
    Narrative("HOOD", "Robinhood", 0.8, (0.50, 0.24, 0.26), ["earnings"], co_mentions=["COIN", "SOFI"]),
    Narrative("SOFI", "SoFi", 0.9, (0.52, 0.22, 0.26), [], co_mentions=["HOOD"]),
    Narrative("GLD", "Gold ETF", 0.6, (0.46, 0.24, 0.30), ["fed"]),
]


def event_factor(ev: Event, hour_offset: float) -> float:
    """Multiplier contribution of an event at `hour_offset` hours before now.
    Fast ramp to peak, exponential decay afterwards."""
    start = ev.hours_ago
    t = start - hour_offset  # hours since event start (negative = not started)
    if t < 0:
        return 0.0
    ramp = min(1.0, t / max(1.0, ev.duration * 0.15))
    decay = math.exp(-max(0.0, t - ev.duration * 0.15) / (ev.duration * 0.45))
    return ev.multiplier * ramp * decay


def diurnal(ts: datetime) -> float:
    """US-market-hours hump: quiet overnight, busy 9:30–16:00 ET."""
    h = (ts.hour - 14) % 24  # 14 UTC ≈ 9-10am ET
    return 0.35 + 0.65 * math.exp(-((h - 3.5) ** 2) / 18.0)


def pick_stance(rng: random.Random, mix: tuple[float, float, float]) -> str:
    return rng.choices(["bull", "bear", "neutral"], weights=mix)[0]


def make_text(rng: random.Random, n: Narrative, stance: str, theme: str | None) -> str:
    sym = f"${n.ticker}"
    if theme and rng.random() < 0.55:
        tpl = rng.choice(THEME_TEMPLATES[theme])
    else:
        bank = {"bull": BULL, "bear": BEAR, "neutral": NEUTRAL}[stance]
        tpl = rng.choice(bank)
    text = tpl.format(sym=sym, name=n.name)
    # Sprinkle co-mentions for the relationship graph.
    if n.co_mentions and rng.random() < 0.18:
        other = rng.choice(n.co_mentions)
        text += f" Also watching ${other}."
    return text


def engagement_for(rng: random.Random, platform: str) -> int:
    scale = {"reddit": 18, "stocktwits": 4, "bluesky": 6, "hackernews": 12}[platform]
    return max(0, int(rng.paretovariate(1.5) * scale) - scale)


def generate(n_target: int, seed: int, now: datetime | None = None) -> list[dict]:
    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    # Total expected posts under multipliers; scale rates to hit n_target.
    expected = 0.0
    for nar in NARRATIVES:
        for h in range(HOURS):
            ts = now - timedelta(hours=h)
            f = 1.0 + sum(event_factor(ev, h) for ev in nar.events)
            expected += nar.base_rate * f * diurnal(ts)
    expected += len(MACRO_NOTICKER) * HOURS * 0.05
    scale = n_target / expected

    posts: list[dict] = []
    uid = 0
    for nar in NARRATIVES:
        for h in range(HOURS):
            ts_hour = now - timedelta(hours=h)
            factor = 1.0 + sum(event_factor(ev, h) for ev in nar.events)
            lam = nar.base_rate * factor * diurnal(ts_hour) * scale
            count = _poisson(rng, lam)
            # Active event recolors sentiment + theme while it dominates.
            ev_active = max(nar.events, key=lambda e: event_factor(e, h), default=None)
            ev_weight = event_factor(ev_active, h) if ev_active else 0.0
            for _ in range(count):
                use_event = ev_active is not None and ev_weight > 0.6 and rng.random() < 0.8
                mix = (ev_active.sentiment if use_event and ev_active.sentiment else nar.sentiment)
                theme = (ev_active.theme if use_event and ev_active.theme
                         else (rng.choice(nar.themes) if nar.themes and rng.random() < 0.4 else None))
                stance = pick_stance(rng, mix)
                platform = rng.choices(list(nar.platforms), weights=list(nar.platforms.values()))[0]
                if nar.crypto and platform == "reddit":
                    source = "CryptoCurrency"
                elif platform == "reddit":
                    source = rng.choices(SUBREDDITS[:4], weights=[0.45, 0.25, 0.18, 0.12])[0]
                else:
                    source = platform
                ts = ts_hour - timedelta(minutes=rng.uniform(0, 59))
                uid += 1
                posts.append({
                    "id": f"sample-{uid:06d}",
                    "platform": platform,
                    "source": source,
                    "author": rng.choice(AUTHORS),
                    "text": make_text(rng, nar, stance, theme),
                    "timestamp": ts.isoformat(),
                    "engagement": engagement_for(rng, platform),
                    "url": "",
                    "lang": "en",
                })

    # Ticker-less macro chatter (feeds topic clustering, not the leaderboard).
    for h in range(HOURS):
        ts_hour = now - timedelta(hours=h)
        for _ in range(_poisson(rng, 0.05 * len(MACRO_NOTICKER) * scale * diurnal(ts_hour))):
            uid += 1
            posts.append({
                "id": f"sample-{uid:06d}",
                "platform": rng.choice(["reddit", "bluesky"]),
                "source": rng.choice(["investing", "stocks", "bluesky"]),
                "author": rng.choice(AUTHORS),
                "text": rng.choice(MACRO_NOTICKER),
                "timestamp": (ts_hour - timedelta(minutes=rng.uniform(0, 59))).isoformat(),
                "engagement": engagement_for(rng, "reddit"),
                "url": "",
                "lang": "en",
            })

    posts.extend(price_echo_posts(rng, now, uid))
    posts.sort(key=lambda p: p["timestamp"])
    return posts


# ── price-echo augmentation ──────────────────────────────────────────────
# Plant extra chatter bursts around *real* price-move hours so the flagship
# buzz-vs-price lead/lag readout has genuine structure in demo mode.
# +k → bursts k hours BEFORE big moves (buzz leads); -k → k hours after.
PRICE_ECHO = {"NVDA": +2, "GME": +3, "BTC": +1, "TSLA": -2, "SPY": -1}


def price_echo_posts(rng: random.Random, now: datetime, start_uid: int) -> list[dict]:
    try:
        from worker.ingest.market import fetch_prices

        prices = fetch_prices(list(PRICE_ECHO), days=8, interval="1h")
    except Exception as exc:  # offline — demo still works, just less correlated
        print(f"price-echo skipped ({exc})")
        return []

    name_of = {n.ticker: n.name for n in NARRATIVES}
    rate_of = {n.ticker: n.base_rate for n in NARRATIVES}
    posts: list[dict] = []
    uid = start_uid
    week_ago = now - timedelta(hours=HOURS)
    for ticker, lag in PRICE_ECHO.items():
        rows = prices.get(ticker) or []
        # Hours that actually have a candle — for equities that's market hours
        # only. A burst planted outside them is invisible to the correlation
        # join, so echoes are only placed on candle hours.
        candle_hours = {r["ts"][:13] for r in rows}
        rets = []
        for prev_row, row in zip(rows, rows[1:]):
            ts = datetime.fromisoformat(row["ts"])
            if ts < week_ago or ts > now:
                continue
            if prev_row["close"]:
                rets.append((ts, (row["close"] - prev_row["close"]) / prev_row["close"]))
        if len(rets) < 20:
            continue
        # Top ~12% absolute movers get an echo burst.
        cutoff = sorted((abs(r) for _, r in rets), reverse=True)[max(1, len(rets) // 8)]
        for ts, ret in rets:
            if abs(ret) < cutoff:
                continue
            burst_ts = ts - timedelta(hours=lag)
            if burst_ts < week_ago or burst_ts > now:
                continue
            if burst_ts.isoformat()[:13] not in candle_hours:
                continue
            # Bursts must stand out above the ticker's *organic* hourly chatter
            # or high-volume names drown their own signal.
            n_posts = min(40, _poisson(rng, 5 + abs(ret) * 250 + rate_of.get(ticker, 1.0) * 4))
            bank = BULL if ret > 0 else BEAR
            for _ in range(n_posts):
                uid += 1
                posts.append({
                    "id": f"sample-{uid:06d}",
                    "platform": rng.choices(["stocktwits", "reddit", "bluesky"], weights=[0.5, 0.38, 0.12])[0],
                    "source": "wallstreetbets" if rng.random() < 0.4 else "stocktwits",
                    "author": rng.choice(AUTHORS),
                    "text": rng.choice(bank).format(sym=f"${ticker}", name=name_of.get(ticker, ticker)),
                    # stay strictly inside burst_ts's hour so the burst lands
                    # in exactly one mention bucket
                    "timestamp": (burst_ts.replace(minute=0, second=0, microsecond=0)
                                  + timedelta(minutes=rng.uniform(1, 58))).isoformat(),
                    "engagement": engagement_for(rng, "stocktwits") + int(abs(ret) * 400),
                    "url": "",
                    "lang": "en",
                })
    print(f"price-echo: planted {len(posts)} posts around real price moves")
    return posts


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's algorithm — fine for small lambda."""
    if lam <= 0:
        return 0
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--posts", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()

    posts = generate(args.posts, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                                    "posts": posts}, indent=1), encoding="utf-8")
    print(f"wrote {len(posts)} posts -> {args.out}")


if __name__ == "__main__":
    main()
