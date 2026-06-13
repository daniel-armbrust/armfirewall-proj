"""Load and validate datasets used by the ADAM text classifier."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable

from core import db


def training_run(
    training_uid: str,
    request_uid: str,
    *,
    db_path: Path,
    normalize_uuid: Callable[[object], str],
) -> dict[str, Any]:
    """Return the running database record for one work request."""
    row = db.fetch_one(
        """
        SELECT id, training_uid, work_request_uid, status
        FROM adam_training_runs
        WHERE training_uid = ? AND work_request_uid = ? AND status = 'running'
        """,
        (
            normalize_uuid(training_uid),
            normalize_uuid(request_uid),
        ),
        db_path=db_path,
    )

    if row is None:
        raise ValueError("The running ADAM training run was not found.")

    return row


def training_datasets(
    training_run_id: int,
    *,
    db_path: Path,
    compatible_categories: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Return compatible datasets associated with one training run."""
    rows = db.fetch_all(
        """
        SELECT d.dataset_uid, d.category, d.purpose, d.original_filename,
               d.stored_filepath, d.sha256, d.records
        FROM adam_training_run_datasets AS rd
        JOIN adam_datasets AS d ON d.id = rd.dataset_id
        WHERE rd.training_run_id = ?
        ORDER BY d.category, d.purpose
        """,
        (training_run_id,),
        db_path=db_path,
    )

    compatible = [
        row for row in rows if str(row["category"]) in compatible_categories
    ]

    if not compatible:
        raise ValueError("No compatible datasets are associated with this training run.")

    return compatible


def dataset_path(
    dataset: dict[str, Any],
    *,
    root_dir: Path,
    dataset_dir: Path,
    normalize_uuid: Callable[[object], str],
) -> Path:
    """Resolve and validate one stored dataset path."""
    normalize_uuid(dataset["dataset_uid"])

    path = (root_dir / str(dataset["stored_filepath"])).resolve()
    dataset_root = dataset_dir.resolve()

    if not path.is_relative_to(dataset_root):
        raise ValueError("The dataset path is outside the ADAM dataset directory.")

    if not path.is_file():
        raise FileNotFoundError(f"The dataset file was not found: {path.name}")

    return path


def stored_artifact_path(
    stored_filepath: object,
    *,
    root_dir: Path,
    artifact_root: Path,
    artifact_name: str,
) -> Path:
    """Resolve one stored artifact inside its configured directory."""
    path = (root_dir / str(stored_filepath)).resolve()

    if not path.is_relative_to(artifact_root.resolve()):
        raise ValueError(f"The ADAM {artifact_name} path is invalid.")

    return path


def load_dataset(
    dataset: dict[str, Any],
    *,
    root_dir: Path,
    dataset_dir: Path,
    required_columns: tuple[str, ...],
    normalize_uuid: Callable[[object], str],
) -> tuple[list[str], list[str]]:
    """Load one validated UTF-8 text,label CSV."""
    texts: list[str] = []
    labels: list[str] = []
    
    path = dataset_path(
        dataset,
        root_dir=root_dir,
        dataset_dir=dataset_dir,
        normalize_uuid=normalize_uuid,
    )

    with path.open("r", encoding="utf-8-sig", newline="") as dataset_file:
        reader = csv.DictReader(dataset_file)

        if tuple(reader.fieldnames or ()) != required_columns:
            raise ValueError("The dataset header must be exactly: text,label.")

        for line_number, row in enumerate(reader, start=2):
            text = str(row.get("text") or "").strip()
            label = str(row.get("label") or "").strip()

            if not text or not label:
                raise ValueError(
                    f"Dataset line {line_number} must include both text and label."
                )

            texts.append(text)
            labels.append(label)

    if not texts:
        raise ValueError("The dataset does not contain records.")

    return texts, labels
