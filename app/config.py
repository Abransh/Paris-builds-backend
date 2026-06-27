"""Runtime settings. Override any field via an env var of the same name."""

from __future__ import annotations

import os

from pydantic import BaseModel


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw and raw.strip() else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw and raw.strip() else default


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return raw if raw and raw.strip() else default


class Settings(BaseModel):
    # Refresh loop
    refresh_interval_seconds: int = 60

    # Per-venue fetch shaping
    fetch_limit: int = 150            # top-N markets (by volume) kept per venue
    kalshi_event_pages: int = 10      # max event pages (200/page) to scan before sort
    http_timeout_seconds: float = 10.0
    user_agent: str = "paris-prediction-aggregator/0.1 (+read-only)"

    # Endpoints (read-only, no API key required)
    kalshi_base_url: str = "https://external-api.kalshi.com/trade-api/v2"
    polymarket_base_url: str = "https://gamma-api.polymarket.com"

    # Matching
    match_threshold: float = 0.85     # difflib ratio cutoff for clustering

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            refresh_interval_seconds=_env_int("REFRESH_INTERVAL_SECONDS", 60),
            fetch_limit=_env_int("FETCH_LIMIT", 150),
            kalshi_event_pages=_env_int("KALSHI_EVENT_PAGES", 10),
            http_timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 10.0),
            user_agent=_env_str("USER_AGENT", "paris-prediction-aggregator/0.1 (+read-only)"),
            kalshi_base_url=_env_str("KALSHI_BASE_URL", "https://external-api.kalshi.com/trade-api/v2"),
            polymarket_base_url=_env_str("POLYMARKET_BASE_URL", "https://gamma-api.polymarket.com"),
            match_threshold=_env_float("MATCH_THRESHOLD", 0.85),
        )


settings = Settings.load()
