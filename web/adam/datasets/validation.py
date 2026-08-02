"""Validation helpers for ADAM datasets."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from core.constants import (
    ADAM_DATASET_CATEGORIES,
    ADAM_DATASET_MAX_BYTES,
    ADAM_DATASET_MAX_ROWS,
    ADAM_DATASET_REQUIRED_COLUMNS,
)
from .errors import DatasetUploadError


def _normalize_category(value: str) -> str:
    """Return one supported dataset category."""
    category = value.strip().lower()

    if category not in ADAM_DATASET_CATEGORIES:
        raise DatasetUploadError(
            "Dataset category must be Adam Misc, Firewall, Greetings, or NER."
        )

    return category


def _safe_filename(value: str) -> str:
    """Return a display-only CSV file name without client path components."""
    filename = Path(value.replace("\\", "/")).name.strip()

    if not filename:
        filename = "dataset.csv"

    if len(filename) > 255:
        raise DatasetUploadError("The CSV file name is too long.")

    if not filename.lower().endswith(".csv"):
        raise DatasetUploadError("The file name must end with .csv.")

    return filename


def _inspect_csv(content: bytes) -> tuple[int, list[str]]:
    """Validate one UTF-8 text,label CSV and return its summary."""
    if not content:
        raise DatasetUploadError("The CSV file is empty.")

    if len(content) > ADAM_DATASET_MAX_BYTES:
        raise DatasetUploadError("The CSV file exceeds the 5 MB limit.")

    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetUploadError("The CSV file must use UTF-8 encoding.") from exc

    reader = csv.DictReader(io.StringIO(decoded, newline=""))

    if tuple(reader.fieldnames or ()) != ADAM_DATASET_REQUIRED_COLUMNS:
        raise DatasetUploadError("The header must be exactly: text,label.")

    records = 0
    labels: set[str] = set()

    for line_number, row in enumerate(reader, start=2):
        text = str(row.get("text") or "").strip()
        label = str(row.get("label") or "").strip()

        if not text and not label:
            continue

        if not text or not label:
            raise DatasetUploadError(
                f"Line {line_number} must include both text and label."
            )

        records += 1
        labels.add(label)

        if records > ADAM_DATASET_MAX_ROWS:
            raise DatasetUploadError(
                f"The dataset exceeds the limit of {ADAM_DATASET_MAX_ROWS} records."
            )

    if not records:
        raise DatasetUploadError("The dataset does not contain records.")

    if not labels:
        raise DatasetUploadError("The dataset must contain at least one label.")

    return records, sorted(labels)
