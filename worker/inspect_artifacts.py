"""Quick artifact sanity check: python -m worker.inspect_artifacts"""
import json
from pathlib import Path

base = Path(__file__).parent.parent / "dashboard" / "public" / "data"

t = json.load(open(base / "trending.json"))
print("mood:", t["mood"])
for m in t["tickers"][:8]:
    print(f"{m['ticker']:6} mentions={m['mentions']:4} prev={m['mentions_prev']:4} "
          f"vel={m['velocity']:+.2f} brk={m['breakout_score']:+.2f} "
          f"phase={m['phase']:9} bb={m['bull_bear_ratio']:.2f} sent={m['sentiment_avg']:+.2f}")

n = json.load(open(base / "tickers" / "NVDA.json"))
print("\nNVDA readout:", n["correlation"]["readout"])
print("NVDA prices:", len(n["prices"]), "pts, last close:", n["prices"][-1]["close"])

g = json.load(open(base / "tickers" / "GME.json"))
print("GME phase:", g["trend"]["phase"], "breakout:", g["trend"]["breakout_score"])

topics = json.load(open(base / "topics.json"))
print("\ntopics:", len(topics["topics"]), "points:", len(topics["points"]))
for tp in sorted(topics["topics"], key=lambda x: -x["size"])[:8]:
    print("  ", tp["size"], "·", tp["label"])

a = json.load(open(base / "alerts.json"))
print("\nalerts:", [f"{x['ticker']}:{x['kind']}" for x in a["alerts"]])

graph = json.load(open(base / "graph.json"))
print("graph:", len(graph["nodes"]), "nodes,", len(graph["edges"]), "edges")
