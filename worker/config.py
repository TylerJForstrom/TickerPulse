"""Environment-driven configuration. Every setting has a sane default so the
pipeline runs end-to-end with zero credentials (demo mode)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # .env support for local dev; harmless if absent
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
# Demo-mode artifacts land here and are served as static files by Netlify.
ARTIFACT_DIR = ROOT / "dashboard" / "public" / "data"


def _split(value: str) -> list[str]:
    return [s.strip() for s in value.split(",") if s.strip()]


@dataclass
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")

    reddit_client_id: str = os.getenv("REDDIT_CLIENT_ID", "")
    reddit_client_secret: str = os.getenv("REDDIT_CLIENT_SECRET", "")
    reddit_user_agent: str = os.getenv("REDDIT_USER_AGENT", "TickerPulse/1.0")
    reddit_subreddits: list[str] = field(
        default_factory=lambda: _split(
            os.getenv(
                "REDDIT_SUBREDDITS",
                "wallstreetbets,stocks,investing,options,CryptoCurrency",
            )
        )
    )

    stocktwits_max_symbols: int = int(os.getenv("STOCKTWITS_MAX_SYMBOLS", "30"))

    bluesky_handle: str = os.getenv("BLUESKY_HANDLE", "")
    bluesky_app_password: str = os.getenv("BLUESKY_APP_PASSWORD", "")

    hf_token: str = os.getenv("HF_TOKEN", "")
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")

    window_hours: int = int(os.getenv("PIPELINE_WINDOW_HOURS", "24"))
    bucket_minutes: int = int(os.getenv("PIPELINE_BUCKET_MINUTES", "60"))
    sentiment_backend: str = os.getenv("SENTIMENT_BACKEND", "auto")
    embed_backend: str = os.getenv("EMBED_BACKEND", "auto")

    @property
    def has_db(self) -> bool:
        return bool(self.database_url)


settings = Settings()
