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

    # Future backends:
    # if backend == "turso":
    #     from .turso_store import TursoStore
    #     return TursoStore()
    # if backend == "d1":
    #     from .d1_store import D1Store
    #     return D1Store()

    raise ValueError(f"Unknown storage backend: '{backend}'")
