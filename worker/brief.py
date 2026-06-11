"""Exportable market-chatter brief: a Markdown digest of emerging tickers,
themes, sentiment shifts, and supporting quotes — written for an investing
or fintech-marketing reader. The dashboard serves it as one-click export."""

from __future__ import annotations

from datetime import datetime, timezone


def _arrow(curr: int, prev: int) -> str:
    if prev == 0:
        return "new" if curr else "—"
    pct = (curr - prev) / prev * 100
    return f"{'▲' if pct >= 0 else '▼'} {abs(pct):.0f}%"


def generate_brief(trends: dict[str, dict], mood: dict, topics: list[dict],
                   alerts: list[dict], mode: str) -> str:
    now = datetime.now(timezone.utc)
    ranked = sorted(trends.values(), key=lambda m: -m["breakout_score"])
    emerging = [m for m in ranked if m["phase"] == "emerging"][:5]
    fading = [m for m in ranked if m["phase"] == "fading"][:3]
    by_vol = sorted(trends.values(), key=lambda m: -m["mentions"])[:10]

    lines = [
        "# TickerPulse Market Chatter Brief",
        f"*Generated {now.strftime('%Y-%m-%d %H:%M UTC')} · window: last "
        f"{ranked[0]['window_hours'] if ranked else 24}h · mode: {mode}*",
        "",
        f"## Market mood: {mood['label'].title()} ({mood['index']}/100)",
        f"{mood['bull']} bullish / {mood['bear']} bearish / {mood['neutral']} neutral "
        f"posts across {mood['posts']} scored posts.",
        "",
        "## Emerging tickers",
    ]
    if emerging:
        for m in emerging:
            lines.append(
                f"- **${m['ticker']}** ({m['name']}) — {m['mentions']} mentions "
                f"({_arrow(m['mentions'], m['mentions_prev'])} vs prior window), "
                f"breakout {m['breakout_score']:.1f}σ, bull:bear {m['bull_bear_ratio']:.1f}."
            )
    else:
        lines.append("- Nothing breaking out this window.")

    if fading:
        lines += ["", "## Fading stories"]
        for m in fading:
            lines.append(
                f"- **${m['ticker']}** — chatter cooling "
                f"({m['mentions']} vs {m['mentions_prev']} mentions), "
                f"sentiment {m['sentiment_avg']:+.2f}."
            )

    lines += ["", "## Most discussed", "", "| Ticker | Mentions | Δ | Bull:Bear | Sentiment | Phase |",
              "|---|---|---|---|---|---|"]
    for m in by_vol:
        lines.append(
            f"| ${m['ticker']} | {m['mentions']} | {_arrow(m['mentions'], m['mentions_prev'])} "
            f"| {m['bull_bear_ratio']:.1f} | {m['sentiment_avg']:+.2f} | {m['phase']} |"
        )

    if topics:
        lines += ["", "## Themes in the conversation"]
        for t in sorted(topics, key=lambda t: -t["size"])[:6]:
            ticks = ", ".join(f"${x['ticker']}" for x in t["tickers"][:3])
            lines.append(f"- **{t['label']}** — {t['size']} posts"
                         + (f" (mostly {ticks})" if ticks else "")
                         + f", sentiment {t['sentiment_avg']:+.2f}.")

    if alerts:
        lines += ["", "## Unusual activity"]
        for a in alerts[:6]:
            lines.append(f"- {a['message']}")

    # Supporting quotes: highest-engagement posts among emerging tickers.
    quotes = []
    for m in (emerging or by_vol[:3]):
        if m["top_posts"]:
            p = m["top_posts"][0]
            quotes.append((m["ticker"], p))
    if quotes:
        lines += ["", "## Voices from the crowd"]
        for ticker, p in quotes[:5]:
            lines.append(f"> \"{p['text']}\" — *{p['author']} on {p['platform']}, "
                         f"${ticker}, {p['engagement']} engagement*")
            lines.append("")

    lines += ["", "---",
              "*TickerPulse aggregates public social chatter. Nothing here is financial advice.*"]
    return "\n".join(lines)
