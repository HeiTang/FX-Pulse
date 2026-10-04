"""Atomic JSON file writes shared by rate storage and scraper state."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def atomic_write_json(
    path: Path, payload: object, *, ensure_ascii: bool = True, trailing_newline: bool = False
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.stem}-",
            suffix=".tmp",
            delete=False,
        ) as f:
            temporary = Path(f.name)
            json.dump(payload, f, ensure_ascii=ensure_ascii, indent=2, sort_keys=True)
            if trailing_newline:
                f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
