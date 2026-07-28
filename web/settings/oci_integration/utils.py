from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


def required_single_line(payload: dict[str, Any], field: str) -> str:
    """Return a required configuration value that cannot alter file structure."""
    value = str(payload.get(field, "")).strip()

    if not value:
        raise ValueError(f"{field.replace('_', ' ').title()} is required.")

    if "\n" in value or "\r" in value:
        raise ValueError(f"{field.replace('_', ' ').title()} must be a single line.")

    return value


def atomic_write(path: Path, content: str, *, mode: int = 0o600) -> None:
    """Write one sensitive configuration file without exposing partial contents."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)

    try:
        os.fchmod(descriptor, mode)

        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_path, path)
        path.chmod(mode)
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        finally:
            raise
