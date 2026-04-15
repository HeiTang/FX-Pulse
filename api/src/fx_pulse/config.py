"""Centralized configuration via pydantic-settings.

Priority: env var > .env file > default value
All settings prefixed with FX_ (e.g. FX_DATA_FILE, FX_SCRAPER_TIMEOUT)
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py → fx_pulse(0) → src(1) → api(2) → FX-Pulse(3)
_PROJECT_ROOT = Path(__file__).parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FX_",
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Currencies ─────────────────────────────────────────────────────────────
    base_currency: str = "TWD"
    currencies: list[str] = ["USD", "JPY", "EUR", "GBP", "HKD", "AUD", "KRW", "SGD"]

    # ── Storage ─────────────────────────────────────────────────────────────────
    storage_backend: str = "json"  # "json" | "turso" | "d1"
    data_file: Path = _PROJECT_ROOT / "web" / "src" / "data" / "rates.json"  # json backend

    # ── Scraper ────────────────────────────────────────────────────────────────
    scraper_timeout: int = 20
    scraper_max_retries: int = 5
    scraper_delay_min: float = 1.5
    scraper_delay_max: float = 3.5
    scraper_backoff_cap: float = 60.0

    # ── API Server ─────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["*"]
    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()
