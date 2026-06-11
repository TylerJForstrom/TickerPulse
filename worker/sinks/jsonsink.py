"""JSON artifact sink — demo mode's "database".

Writes the exact payloads the read API serves into dashboard/public/data/,
so Netlify ships them as static files and the dashboard renders end-to-end
with zero credentials."""

from __future__ import annotations

import json
from pathlib import Path

from worker.config import ARTIFACT_DIR


def write_artifacts(payloads: dict[str, object], out_dir: Path | None = None) -> None:
    """payloads: {"trending": {...}, "tickers/NVDA": {...}, ...} — keys are
    paths relative to the data dir, values JSON-serializable."""
    base = out_dir or ARTIFACT_DIR
    for rel, payload in payloads.items():
        path = base / f"{rel}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(payloads)} artifacts -> {base}")
