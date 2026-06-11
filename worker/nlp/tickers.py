"""Ticker extraction: cashtags + curated dictionary + company-name mapping,
with junk disambiguation.

Rules, in order of confidence:
1. Cashtag  ($AAPL, $btc)  → always counts if in dictionary; unknown cashtags
   count only if they look like real symbols (2-5 uppercase letters) and are
   not blocklisted — catches new/small caps without flooding on "$5 says…".
2. Bare symbol (NVDA)      → counts if in dictionary, written in UPPERCASE,
   and not an "ambiguous" symbol (a ticker that is also an English word:
   NOW, NET, ARM, F, T, …). Ambiguous symbols require the cashtag form or a
   company-name alias to count.
3. Company name ("nvidia") → case-insensitive alias phrase match.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DICT_PATH = Path(__file__).parent.parent / "data" / "tickers.json"

CASHTAG_RE = re.compile(r"\$([A-Za-z][A-Za-z.]{0,5})\b")
BARE_RE = re.compile(r"\b([A-Z][A-Z.]{1,5})\b")

# Dictionary tickers that double as English words / common abbreviations.
# Bare-uppercase occurrences of these are ignored (cashtag or alias only).
AMBIGUOUS = {
    "NOW", "NET", "ARM", "ALL", "ANY", "F", "T", "C", "V", "MA", "MS", "GS",
    "GE", "GM", "BA", "KO", "HD", "DIS", "TM", "MU", "SO", "PEP", "CAT",
    "LINK", "PEPE", "GLD", "DASH", "SHOP", "SQ", "IT", "ON", "DOGE",
}


@lru_cache(maxsize=1)
def load_dictionary() -> tuple[dict, set[str], list[tuple[str, str]]]:
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    tickers: dict = data["tickers"]
    blocklist = set(data["blocklist"])
    # (alias phrase, ticker), longest alias first so "palo alto networks"
    # wins over hypothetical shorter overlaps.
    aliases = sorted(
        ((alias, sym) for sym, info in tickers.items() for alias in info.get("aliases", [])),
        key=lambda pair: -len(pair[0]),
    )
    return tickers, blocklist, aliases


@lru_cache(maxsize=1)
def _alias_regexes() -> list[tuple[re.Pattern, str]]:
    _, _, aliases = load_dictionary()
    return [
        (re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE), sym)
        for alias, sym in aliases
    ]


def ticker_name(symbol: str) -> str:
    tickers, _, _ = load_dictionary()
    info = tickers.get(symbol)
    return info["name"] if info else symbol


def ticker_sector(symbol: str) -> str:
    tickers, _, _ = load_dictionary()
    info = tickers.get(symbol)
    return info["sector"] if info else "Other"


def extract_tickers(text: str) -> list[str]:
    """Return unique tickers mentioned in `text`, most-confident first."""
    tickers, blocklist, _ = load_dictionary()
    found: dict[str, None] = {}  # ordered set

    # 1. Cashtags — highest confidence.
    for m in CASHTAG_RE.finditer(text):
        sym = m.group(1).upper()
        if sym in tickers:
            found.setdefault(sym)
        elif sym not in blocklist and re.fullmatch(r"[A-Z]{2,5}", sym):
            found.setdefault(sym)  # plausible unknown small-cap cashtag

    # 2. Bare uppercase symbols — dictionary-gated, ambiguity-filtered.
    for m in BARE_RE.finditer(text):
        sym = m.group(1)
        if sym in tickers and sym not in AMBIGUOUS and sym not in blocklist:
            found.setdefault(sym)

    # 3. Company-name aliases.
    for pattern, sym in _alias_regexes():
        if sym not in found and pattern.search(text):
            found.setdefault(sym)

    return list(found)


def tag_posts(posts) -> None:
    """Fill `post.tickers` in place for posts that don't already carry tags
    (StockTwits arrives pre-tagged; everything else is extracted)."""
    for post in posts:
        extracted = extract_tickers(post.text)
        merged = list(dict.fromkeys([*post.tickers, *extracted]))
        post.tickers = merged
