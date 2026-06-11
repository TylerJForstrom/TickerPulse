"""Adapter contract + registry.

An adapter is anything that can produce normalized Posts. `available()`
lets the pipeline skip sources whose credentials aren't configured instead
of failing — demo mode is just "no adapters available except the sample"."""

from __future__ import annotations

import abc
from typing import Iterable, Type

from worker.models import Post

registry: dict[str, Type["Adapter"]] = {}


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
