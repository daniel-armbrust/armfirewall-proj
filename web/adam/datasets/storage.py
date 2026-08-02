"""Filesystem persistence helpers for ADAM datasets."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _write_dataset(path: Path, content: bytes) -> None:
    """Atomically write one private dataset file."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)

    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}-",
        suffix=".tmp",
    )

    temporary_path = Path(temporary_name)

    try:
        os.fchmod(descriptor, 0o640)

        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
