"""Quick artifact sanity check: python -m worker.inspect_artifacts"""

import json
from pathlib import Path

base = Path(__file__).parent.parent / "dashboard" / "public" / "data"


def load(*parts: str) -> dict:
    """Read an artifact. `json.load(open(...))` leaks the handle until the
    refcount happens to drop it, which is not guaranteed outside CPython."""
    return json.loads(base.joinpath(*parts).read_text(encoding="utf-8"))


t = load("trending.json")
print("mood:", t["mood"])
for m in t["tickers"][:8]:
    print(
        f"{m['ticker']:6} mentions={m['mentions']:4} prev={m['mentions_prev']:4} "
        f"vel={m['velocity']:+.2f} brk={m['breakout_score']:+.2f} "
        f"phase={m['phase']:9} bb={m['bull_bear_ratio']:.2f} sent={m['sentiment_avg']:+.2f}"
    )

n = load("tickers", "NVDA.json")
print("\nNVDA readout:", n["correlation"]["readout"])
print("NVDA prices:", len(n["prices"]), "pts, last close:", n["prices"][-1]["close"])

g = load("tickers", "GME.json")
print("GME phase:", g["trend"]["phase"], "breakout:", g["trend"]["breakout_score"])

topics = load("topics.json")
print("\ntopics:", len(topics["topics"]), "points:", len(topics["points"]))
for tp in sorted(topics["topics"], key=lambda x: -x["size"])[:8]:
    print("  ", tp["size"], "·", tp["label"])

a = load("alerts.json")
print("\nalerts:", [f"{x['ticker']}:{x['kind']}" for x in a["alerts"]])

graph = load("graph.json")
print("graph:", len(graph["nodes"]), "nodes,", len(graph["edges"]), "edges")
