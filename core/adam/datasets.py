"""Validation and persistence helpers for ADAM training datasets."""

from __future__ import annotations

import csv
import io
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


DATASET_DIR = Path(__file__).resolve().parent / "files"
TRAINING_DATASET_PATH = DATASET_DIR / "training_dataset.csv"
MAX_DATASET_BYTES = 5 * 1024 * 1024
MAX_DATASET_ROWS = 100_000
REQUIRED_COLUMNS = ("text", "label")


class DatasetValidationError(ValueError):
    """Raised when an uploaded training dataset is invalid."""


def _decode_csv(content: bytes) -> str:
    """Decode one UTF-8 CSV payload, accepting an optional BOM."""
    if not content:
        raise DatasetValidationError("The CSV file is empty.")
    if len(content) > MAX_DATASET_BYTES:
        raise DatasetValidationError("The CSV file exceeds the 5 MB limit.")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetValidationError("The CSV file must use UTF-8 encoding.") from exc


def normalize_training_dataset(content: bytes) -> tuple[bytes, dict[str, Any]]:
    """Validate and normalize a training dataset CSV payload."""
    text = _decode_csv(content)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    columns = tuple(reader.fieldnames or ())
    if columns != REQUIRED_COLUMNS:
        expected = ",".join(REQUIRED_COLUMNS)
        raise DatasetValidationError(f"The header must be exactly: {expected}.")

    rows: list[tuple[str, str]] = []
    labels: set[str] = set()
    for line_number, row in enumerate(reader, start=2):
        sample_text = str(row.get("text") or "").strip()
        label = str(row.get("label") or "").strip()
        if not sample_text and not label:
            continue
        if not sample_text or not label:
            raise DatasetValidationError(
                f"Line {line_number} must include both text and label."
            )
        rows.append((sample_text, label))
        labels.add(label)
        if len(rows) > MAX_DATASET_ROWS:
            raise DatasetValidationError(
                f"The dataset exceeds the limit of {MAX_DATASET_ROWS} records."
            )

    if not rows:
        raise DatasetValidationError("The dataset does not contain training records.")
    if len(labels) < 2:
        raise DatasetValidationError("The dataset must contain at least two labels.")

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(REQUIRED_COLUMNS)
    writer.writerows(rows)
    normalized = output.getvalue().encode("utf-8")
    return normalized, {
        "rows": len(rows),
        "intentions": len(labels),
        "size_bytes": len(normalized),
    }


def save_training_dataset(content: bytes, *, original_name: str = "") -> dict[str, Any]:
    """Validate and atomically replace the active ADAM training dataset."""
    normalized, details = normalize_training_dataset(content)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_path = tempfile.mkstemp(
        dir=DATASET_DIR,
        prefix=".training-dataset-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(normalized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, TRAINING_DATASET_PATH)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise

    return details | {
        "file_name": TRAINING_DATASET_PATH.name,
        "original_name": Path(original_name).name,
        "updated_at": datetime.fromtimestamp(
            TRAINING_DATASET_PATH.stat().st_mtime
        ).astimezone().isoformat(timespec="seconds"),
    }


def training_dataset_info() -> dict[str, Any] | None:
    """Return metadata for the active training dataset, when present."""
    if not TRAINING_DATASET_PATH.is_file():
        return None
    _, details = normalize_training_dataset(TRAINING_DATASET_PATH.read_bytes())
    return details | {
        "file_name": TRAINING_DATASET_PATH.name,
        "updated_at": datetime.fromtimestamp(
            TRAINING_DATASET_PATH.stat().st_mtime
        ).astimezone().isoformat(timespec="seconds"),
    }
