"""Persist source cooldowns between CLI invocations and scheduled runners."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from ..config import settings
from ..json_io import atomic_write_json


class SourceCooldown(BaseModel):
    consecutive_blocks: int = Field(ge=1)
    next_retry_at: datetime

    @field_validator("next_retry_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Cooldown timestamps must include a timezone")
        return value


class CooldownState(BaseModel):
    sources: dict[str, SourceCooldown]


class Cooldowns:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.scraper_state_file
        # Invalid state must fail rather than silently bypass an existing cooldown.
        self.state = (
            CooldownState.model_validate_json(self.path.read_text())
            if self.path.exists()
            else CooldownState(sources={})
        )

    def active(self, source: str, now: datetime | None = None) -> SourceCooldown | None:
        entry = self.state.sources.get(source)
        return entry if entry and entry.next_retry_at > (now or datetime.now(UTC)) else None

    def block(
        self,
        source: str,
        retry_after_seconds: float | None = None,
        now: datetime | None = None,
    ) -> SourceCooldown:
        now = now or datetime.now(UTC)
        previous = self.state.sources.get(source)
        count = previous.consecutive_blocks + 1 if previous else 1
        seconds = max(6 * 3600 * 2 ** min(count - 1, 2), retry_after_seconds or 0)
        # A server deadline can be longer than our normal 24-hour backoff cap.
        try:
            deadline = now + timedelta(seconds=seconds)
        except OverflowError:
            deadline = datetime.max.replace(tzinfo=UTC)
        if previous:
            deadline = max(deadline, previous.next_retry_at)
        entry = SourceCooldown(consecutive_blocks=count, next_retry_at=deadline)
        self.state.sources[source] = entry
        self._save()
        return entry

    def success(self, source: str) -> None:
        if self.state.sources.pop(source, None) is not None:
            self._save()

    def _save(self) -> None:
        atomic_write_json(self.path, self.state.model_dump(mode="json"), trailing_newline=True)
