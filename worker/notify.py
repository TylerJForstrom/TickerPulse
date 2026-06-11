"""Alert notifications → Discord webhook (optional, env-gated).

Set DISCORD_WEBHOOK_URL (a channel webhook from Discord → channel settings →
Integrations → Webhooks) and the worker pushes *new* unusual-activity alerts
each run. Alerts already sent in the previous run are skipped, so a spike
pings once, not every 15 minutes."""

from __future__ import annotations

import os

KIND_EMOJI = {
    "mention_spike": "🚨",
    "bullish_surge": "🟢",
    "bearish_turn": "🔴",
    "new_entrant": "✨",
}


def alert_key(a: dict) -> str:
    return f"{a['ticker']}:{a['kind']}"


def send_discord_alerts(alerts: list[dict], previous_alerts: list[dict],
                        dashboard_url: str = "https://tickerpulse-demo.netlify.app") -> int:
    """Returns the number of alerts sent (0 when unconfigured or nothing new)."""
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook or not alerts:
        return 0
    already = {alert_key(a) for a in previous_alerts}
    fresh = [a for a in alerts if alert_key(a) not in already][:6]
    if not fresh:
        return 0

    import requests

    lines = [
        f"{KIND_EMOJI.get(a['kind'], '⚡')} **${a['ticker']}** — {a['message']}"
        for a in fresh
    ]
    payload = {
        "username": "TickerPulse",
        "embeds": [{
            "title": "Unusual social activity",
            "description": "\n".join(lines),
            "url": dashboard_url,
            "color": 0x60A5FA,
            "footer": {"text": "TickerPulse · not financial advice"},
        }],
    }
    try:
        resp = requests.post(webhook, json=payload, timeout=20)
        resp.raise_for_status()
        return len(fresh)
    except Exception as exc:  # notification failure must never fail the run
        print(f"discord webhook failed: {exc}")
        return 0
