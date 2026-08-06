"""Adapter contract + registry.

An adapter is anything that can produce normalized Posts. `available()`
lets the pipeline skip sources whose credentials aren't configured instead
of failing — demo mode is just "no adapters available except the sample"."""

from __future__ import annotations

import abc
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Iterator, Type

from worker.models import Post

registry: dict[str, Type["Adapter"]] = {}


def drain_pages(
    pages: Iterator[list],
    *,
    lookback_hours: int,
    max_pages: int,
    label: str,
    ts: Callable = lambda item: item.timestamp,
) -> list:
    """Drain a newest-first paged listing until it covers the lookback window.

    GitHub's shared cron scheduler drops most of this pipeline's ticks
    (measured 10-16 runs/day against 96 requested, gaps up to ~3h35m), so a
    single fixed-depth page silently loses whatever scrolled past that depth
    during a gap — and those posts are unrecoverable afterwards. Paginating
    adapters walk pages until the oldest item on a page falls outside
    `lookback_hours`, the source is exhausted (the generator stops or yields
    an empty page), or `max_pages` is hit.

    Hitting the cap while every item seen is still inside the window means
    the listing outran the budget: a `[saturation]` line is printed so the
    run log records exactly when coverage was incomplete — the only
    observable trace, since the missed posts themselves are never seen.

    `pages` yields one list of items per page (fetched lazily); `ts` maps an
    item to its tz-aware UTC timestamp. Returns the concatenated items.
    """
    horizon = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    items: list = []
    pages_used = 0
    for page in pages:
        pages_used += 1
        items.extend(page)
        if not page or min(ts(item) for item in page) <= horizon:
            return items  # window covered or source exhausted
        if pages_used >= max_pages:
            print(
                f"  [saturation] {label}: {max_pages}-page budget spent with every "
                f"item still inside the {lookback_hours}h lookback — listing deeper "
                f"than budget, older posts may be missed"
            )
            return items
    return items


class Adapter(abc.ABC):
    """Base class for all sources (Reddit, StockTwits, Bluesky, files…)."""

    name: str = "base"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.name != "base":
            registry[cls.name] = cls

    @abc.abstractmethod
    def available(self) -> bool:
        """True when this source is usable (credentials present, etc.)."""

    @abc.abstractmethod
    def fetch(self) -> Iterable[Post]:
        """Yield normalized posts. Implementations must be polite: respect
        rate limits, cache aggressively, and never raise on partial data."""
