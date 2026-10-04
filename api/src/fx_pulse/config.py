"""Centralized configuration via pydantic-settings.

Priority: env var > .env file > default value
All settings prefixed with FX_ (e.g. FX_DATA_FILE, FX_SCRAPER_TIMEOUT)
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
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
    storage_backend: str = "json"  # Only the JSON backend is implemented.
    data_file: Path = _PROJECT_ROOT / "web" / "src" / "data" / "rates.json"  # json backend

    scraper_state_file: Path = _PROJECT_ROOT / "api" / "scrape_state.json"

    # ── Scraper ────────────────────────────────────────────────────────────────
    scraper_timeout: int = Field(default=20, gt=0)
    scraper_max_retries: int = Field(default=3, ge=1, le=10)
    scraper_delay_min: float = Field(default=3.0, ge=0, allow_inf_nan=False)
    scraper_delay_max: float = Field(default=6.0, ge=0, allow_inf_nan=False)
    scraper_backoff_cap: float = Field(default=60.0, gt=0, allow_inf_nan=False)
    scraper_backoff_base: float = Field(default=5.0, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_delays(self) -> Settings:
        if self.scraper_delay_max < self.scraper_delay_min:
            raise ValueError("scraper_delay_max must be >= scraper_delay_min")
        return self

    # ── API Server ─────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["*"]
    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()
