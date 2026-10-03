"""Store factory — returns the correct backend based on settings."""

from __future__ import annotations

from functools import lru_cache

from ..config import settings
from .base import BaseStore


@lru_cache(maxsize=1)
def get_store() -> BaseStore:
    backend = settings.storage_backend

    if backend == "json":
        from .json_store import JsonStore

        return JsonStore()

    raise ValueError(f"Unknown storage backend: '{backend}'")
