"""Finance sentiment: bull / bear / neutral per post.

Backends, selected by SENTIMENT_BACKEND (default `auto`):
- `finbert`  — ProsusAI/finbert via local transformers. The real deal; runs
               in the GitHub Actions worker where the ML extras are installed.
- `hf_api`   — same model via Hugging Face serverless Inference API (needs
               HF_TOKEN); zero local ML deps.
- `lexicon`  — built-in finance lexicon scorer. No deps, no credentials:
               powers demo mode and acts as the universal fallback.
`auto` picks the best available: finbert → hf_api → lexicon.
"""

from __future__ import annotations

import math
import re
from typing import Iterable

from worker.config import settings
from worker.models import Post

LABELS = ("bull", "bear", "neutral")

# ── lexicon backend ──────────────────────────────────────────────────────
# Weighted finance phrases. Multi-word entries are matched first.
BULL_TERMS = {
    "to the moon": 3.0, "moon": 1.5, "rip higher": 2.5, "ripping": 2.0,
    "breakout": 2.0, "breaking out": 2.2, "beat estimates": 2.5, "beat": 1.2,
    "raised guidance": 2.5, "guide raised": 2.5, "guidance was a beat": 2.5,
    "all-time high": 2.0, "new highs": 2.0, "record": 1.2, "rally": 1.8,
    "bullish": 2.5, "calls": 1.0, "calls printing": 3.0, "printing": 1.5,
    "undervalued": 2.0, "cheap": 1.2, "accumulating": 1.8, "accumulation": 1.5,
    "buy the dip": 2.0, "dip was a gift": 2.5, "loading up": 2.0, "loaded up": 2.0,
    "strong hands": 1.5, "diamond hands": 2.0, "not selling": 1.5,
    "squeeze": 1.8, "gamma ramp": 2.0, "shorts are trapped": 2.8,
    "short interest is fuel": 2.5, "executing flawlessly": 2.5,
    "has legs": 2.0, "next leg up": 2.2, "thesis keeps getting stronger": 2.5,
    "up only": 2.0, "outperform": 1.8, "upgrade": 1.8, "upgraded": 1.8,
    "demand is bottomless": 2.5, "backlog at record": 2.2, "paying off": 1.8,
    "bullish continuation": 2.5, "reclaimed": 1.5, "best risk/reward": 2.2,
    "decoupling is real": 1.5, "institutions are here": 1.8, "inflows": 1.5,
    "leading the charge": 1.8, "positioned perfectly": 2.2, "winner": 1.5,
    "crushing it": 2.2, "underrated": 1.5, "quietly at all-time highs": 2.2,
}
BEAR_TERMS = {
    "puts": 1.2, "puts printing": 3.0, "bearish": 2.5, "crash": 2.5,
    "rolls over": 2.0, "rolling over": 2.0, "breaking down": 2.2,
    "below support": 2.0, "bear flag": 2.5, "rug pull": 2.5, "dump": 1.8,
    "dumping": 2.0, "insiders dumping": 2.8, "sell off": 2.0, "selloff": 2.0,
    "overvalued": 2.2, "priced for perfection": 2.5, "makes zero sense": 2.0,
    "bagholder": 2.5, "bag holder": 2.5, "wait for the flush": 2.2,
    "margins are getting crushed": 2.8, "margin death spiral": 3.0,
    "guidance was weak": 2.5, "missed estimates": 2.5, "miss": 1.2,
    "downgrade": 1.8, "downgraded": 1.8, "exhausted": 1.8, "euphoric": 1.5,
    "taking profits": 1.5, "sold all": 2.0, "momentum is gone": 2.2,
    "in trouble": 2.0, "not good": 1.8, "numbers don't add up": 2.5,
    "don't add up": 2.2, "giving back": 1.8, "underwhelmed": 2.0,
    "bulls in denial": 2.5, "softening": 1.5, "cutting prices": 1.5,
    "getting crushed": 2.5, "worry": 1.2, "scam": 2.5, "fraud": 2.8,
    "drilling": 1.8, "tanking": 2.5, "capitulation": 2.0, "short it": 2.2,
}
NEGATORS = re.compile(r"\b(not|no|never|isn't|aren't|won't|don't|doesn't|wasn't)\s+(\w+\s+){0,2}$")
INTENSIFIERS = {"absolutely": 1.4, "insanely": 1.4, "massively": 1.3, "huge": 1.2, "very": 1.15}


def _lexicon_score(text: str) -> float:
    """Signed score, roughly -1..+1 after squashing."""
    t = " " + text.lower() + " "
    raw = 0.0
    for terms, sign in ((BULL_TERMS, 1.0), (BEAR_TERMS, -1.0)):
        for phrase, weight in terms.items():
            idx = 0
            while True:
                idx = t.find(phrase, idx)
                if idx == -1:
                    break
                w = weight
                prefix = t[max(0, idx - 30): idx]
                if NEGATORS.search(prefix):
                    w = -w * 0.8  # "not selling" flips bear→bull etc.
                for intens, mult in INTENSIFIERS.items():
                    if prefix.rstrip().endswith(intens):
                        w *= mult
                raw += sign * w
                idx += len(phrase)
    return math.tanh(raw / 4.0)


def _label(score: float, threshold: float = 0.12) -> str:
    if score > threshold:
        return "bull"
    if score < -threshold:
        return "bear"
    return "neutral"


def score_lexicon(posts: list[Post]) -> None:
    for p in posts:
        s = _lexicon_score(p.text)
        p.sentiment_score = round(s, 4)
        p.sentiment = _label(s)


# ── FinBERT backends ─────────────────────────────────────────────────────

FINBERT_MODEL = "ProsusAI/finbert"
# FinBERT labels → ours. positive=bull, negative=bear.
FINBERT_MAP = {"positive": "bull", "negative": "bear", "neutral": "neutral"}


def score_finbert_local(posts: list[Post], batch_size: int = 32) -> None:
    from transformers import pipeline  # heavy import, Actions-only

    clf = pipeline("text-classification", model=FINBERT_MODEL, top_k=None, truncation=True)
    texts = [p.text[:512] for p in posts]
    for i in range(0, len(texts), batch_size):
        batch = texts[i: i + batch_size]
        for post, scores in zip(posts[i: i + batch_size], clf(batch)):
            by_label = {FINBERT_MAP[s["label"]]: s["score"] for s in scores}
            signed = by_label.get("bull", 0) - by_label.get("bear", 0)
            post.sentiment_score = round(signed, 4)
            post.sentiment = max(by_label, key=by_label.get)


def score_hf_api(posts: list[Post], batch_size: int = 50) -> None:
    import requests

    url = f"https://api-inference.huggingface.co/models/{FINBERT_MODEL}"
    headers = {"Authorization": f"Bearer {settings.hf_token}"}
    for i in range(0, len(posts), batch_size):
        chunk = posts[i: i + batch_size]
        resp = requests.post(
            url, headers=headers,
            json={"inputs": [p.text[:512] for p in chunk], "options": {"wait_for_model": True}},
            timeout=120,
        )
        resp.raise_for_status()
        for post, scores in zip(chunk, resp.json()):
            by_label = {FINBERT_MAP[s["label"]]: s["score"] for s in scores}
            signed = by_label.get("bull", 0) - by_label.get("bear", 0)
            post.sentiment_score = round(signed, 4)
            post.sentiment = max(by_label, key=by_label.get)


def _finbert_available() -> bool:
    try:
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def score_posts(posts: list[Post], backend: str | None = None) -> str:
    """Score all posts in place; returns the backend actually used."""
    backend = backend or settings.sentiment_backend
    if backend == "auto":
        if _finbert_available():
            backend = "finbert"
        elif settings.hf_token:
            backend = "hf_api"
        else:
            backend = "lexicon"
    if backend == "finbert":
        score_finbert_local(posts)
    elif backend == "hf_api":
        try:
            score_hf_api(posts)
        except Exception as exc:  # API hiccup → degrade, never fail the run
            print(f"hf_api failed ({exc}); falling back to lexicon")
            backend = "lexicon"
            score_lexicon(posts)
    else:
        backend = "lexicon"
        score_lexicon(posts)
    return backend
