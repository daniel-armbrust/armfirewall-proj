"""Safe filesystem access for text-classification artifacts."""

from __future__ import annotations

from pathlib import Path

from core.constants import ADAM_CHARTS_DIR, ROOT_DIR

from .errors import TextClassificationStorageError


def chart_path(chart_filepath: str) -> Path:
    """Resolve a stored chart path while constraining it to ADAM's chart directory."""
    path = (ROOT_DIR / chart_filepath).resolve()

    if not path.is_relative_to(ADAM_CHARTS_DIR.resolve()):
        raise TextClassificationStorageError("The text classification chart path is invalid.")

    return path
