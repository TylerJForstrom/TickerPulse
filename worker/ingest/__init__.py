"""Pluggable source adapters. Each adapter yields normalized Posts; the
pipeline composes whichever adapters have credentials configured, so the
same code runs as a cron batch today or an always-on streamer later."""

from worker.ingest.base import Adapter, registry  # noqa: F401
