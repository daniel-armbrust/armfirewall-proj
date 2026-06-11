"""Validation and persistence helpers for ADAM training datasets."""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from core.constants import ADAM_DATASET_DIR


ACTIVE_DATASET_PATH = ADAM_DATASET_DIR / "active.json"
SOURCE_FILE_NAME = "source.csv"
METADATA_FILE_NAME = "metadata.json"
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


def _atomic_write(path: Path, content: bytes) -> None:
    """Atomically write one private runtime data file."""
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}-",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(file_descriptor, 0o640)
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _json_bytes(value: dict[str, Any]) -> bytes:
    """Encode metadata deterministically as UTF-8 JSON."""
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _normalize_dataset_id(value: object) -> str:
    """Return a canonical UUID and reject paths or arbitrary identifiers."""
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DatasetValidationError("The active dataset identifier is invalid.") from exc


def _safe_file_name(value: str) -> str:
    """Remove client-supplied directory components from a display name."""
    return Path(value.replace("\\", "/")).name or SOURCE_FILE_NAME


def save_training_dataset(content: bytes, *, original_name: str = "") -> dict[str, Any]:
    """Store an immutable dataset and atomically make it active."""
    normalized, details = normalize_training_dataset(content)
    ADAM_DATASET_DIR.mkdir(parents=True, exist_ok=True, mode=0o750)

    dataset_id = str(uuid4())
    dataset_dir = ADAM_DATASET_DIR / dataset_id
    temporary_dir = Path(
        tempfile.mkdtemp(dir=ADAM_DATASET_DIR, prefix=f".upload-{dataset_id}-")
    )
    os.chmod(temporary_dir, 0o750)
    safe_original_name = _safe_file_name(original_name)
    updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    metadata = details | {
        "dataset_id": dataset_id,
        "file_name": safe_original_name,
        "original_name": safe_original_name,
        "source_file": SOURCE_FILE_NAME,
        "updated_at": updated_at,
    }

    try:
        _atomic_write(temporary_dir / SOURCE_FILE_NAME, normalized)
        _atomic_write(temporary_dir / METADATA_FILE_NAME, _json_bytes(metadata))
        os.replace(temporary_dir, dataset_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise

    _atomic_write(ACTIVE_DATASET_PATH, _json_bytes({"dataset_id": dataset_id}))
    return metadata


def training_dataset_info() -> dict[str, Any] | None:
    """Return validated metadata for the active training dataset."""
    if not ACTIVE_DATASET_PATH.is_file():
        return None

    try:
        active = json.loads(ACTIVE_DATASET_PATH.read_text(encoding="utf-8"))
        dataset_id = _normalize_dataset_id(active.get("dataset_id"))
        dataset_dir = ADAM_DATASET_DIR / dataset_id
        source_path = dataset_dir / SOURCE_FILE_NAME
        metadata_path = dataset_dir / METADATA_FILE_NAME
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        raise DatasetValidationError("The active dataset metadata is invalid.") from exc

    if _normalize_dataset_id(metadata.get("dataset_id")) != dataset_id:
        raise DatasetValidationError("The active dataset metadata is inconsistent.")

    try:
        _, details = normalize_training_dataset(source_path.read_bytes())
    except OSError as exc:
        raise DatasetValidationError("The active dataset file is not available.") from exc

    return metadata | details | {"dataset_id": dataset_id}
