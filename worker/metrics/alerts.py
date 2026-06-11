"""Unusual-activity detection: abnormal mention spikes, sentiment flips,
and brand-new entrants to the conversation."""

from __future__ import annotations

from datetime import datetime, timezone


def detect_alerts(trends: dict[str, dict]) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    alerts: list[dict] = []
    for t, m in trends.items():
        if m["breakout_score"] >= 2.0 and m["mentions"] >= 10:
            alerts.append({
                "ticker": t, "kind": "mention_spike", "score": m["breakout_score"],
                "message": (f"${t} mention volume is {m['breakout_score']:.1f}σ above its trailing "
                            f"baseline ({m['mentions']} mentions/{m['window_hours']}h, phase: {m['phase']})."),
                "created_at": now,
            })
        if m["mentions_prev"] >= 5 and m["mentions"] >= 5:
            # Sentiment flip: window avg crossed zero with conviction.
            if m["sentiment_avg"] <= -0.25 and m["bull_bear_ratio"] < 0.6:
                alerts.append({
                    "ticker": t, "kind": "bearish_turn", "score": abs(m["sentiment_avg"]),
                    "message": (f"${t} sentiment has turned decisively bearish "
                                f"(bull:bear {m['bull_bear_ratio']:.2f}, avg {m['sentiment_avg']:+.2f})."),
                    "created_at": now,
                })
            elif m["sentiment_avg"] >= 0.35 and m["bull_bear_ratio"] > 3.0 and m["breakout_score"] > 1.0:
                alerts.append({
                    "ticker": t, "kind": "bullish_surge", "score": m["sentiment_avg"],
                    "message": (f"${t} is seeing a bullish surge "
                                f"(bull:bear {m['bull_bear_ratio']:.2f} on {m['mentions']} mentions)."),
                    "created_at": now,
                })
        if m["mentions_prev"] == 0 and m["mentions"] >= 8:
            alerts.append({
                "ticker": t, "kind": "new_entrant", "score": float(m["mentions"]),
                "message": f"${t} entered the conversation from zero — {m['mentions']} mentions in the last window.",
                "created_at": now,
            })
    alerts.sort(key=lambda a: -a["score"])
    return alerts[:20]
