"""ADAM dataset workflow orchestration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from core import db
from core.constants import ADAM_DATASET_DIR, ADAM_DATASET_TYPES, ADAM_DB_PATH

from .errors import DatasetStateError, DatasetStorageError, DatasetUploadError
from .repository import _active_dataset, _pair_response
from .storage import _write_dataset
from .validation import _inspect_csv, _normalize_category, _safe_filename


def _store_training_dataset(
    content: bytes,
    original_filename: str,
    category: str,
) -> dict[str, object]:
    """Store a new active training CSV and begin a new category pair."""
    records, labels = _inspect_csv(content)
    filename = _safe_filename(original_filename)
    dataset_uid = str(uuid4())
    dataset_path = ADAM_DATASET_DIR / f"{dataset_uid}.csv"
    stored_filepath = str(Path("daemons") / "adamd" / "datasets" / dataset_path.name)
    digest = hashlib.sha256(content).hexdigest()

    try:
        _write_dataset(dataset_path, content)

        with db.transaction(ADAM_DB_PATH) as connection:
            db.execute_on(
                connection,
                """
                UPDATE adam_datasets
                SET status = 'archived', is_active = 0
                WHERE category = ? AND is_active = 1
                """,
                (category,),
            )

            db.execute_on(
                connection,
                """
                INSERT INTO adam_datasets (
                    dataset_uid, category, purpose, original_filename,
                    stored_filepath, sha256, records, labels, labels_count
                )
                VALUES (?, ?, 'training', ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_uid,
                    category,
                    filename,
                    stored_filepath,
                    digest,
                    records,
                    json.dumps(labels, ensure_ascii=False),
                    len(labels),
                ),
            )

            dataset = _pair_response(connection, category)
    except (OSError, db.DatabaseError, RuntimeError) as exc:
        dataset_path.unlink(missing_ok=True)
        raise DatasetStorageError("The dataset could not be stored.") from exc

    if dataset is None:
        dataset_path.unlink(missing_ok=True)
        raise DatasetStorageError("The dataset could not be registered.")

    return dataset


def _store_testing_dataset(
    content: bytes,
    original_filename: str,
    category: str,
) -> dict[str, object]:
    """Store or replace the active testing CSV for one category."""
    records, labels = _inspect_csv(content)
    filename = _safe_filename(original_filename)
    dataset_uid = str(uuid4())
    dataset_path = ADAM_DATASET_DIR / f"{dataset_uid}.csv"
    stored_filepath = str(Path("daemons") / "adamd" / "datasets" / dataset_path.name)
    digest = hashlib.sha256(content).hexdigest()

    try:
        with db.transaction(ADAM_DB_PATH) as connection:
            training = _active_dataset(connection, category, "training")

            if training is None:
                raise DatasetStateError(
                    "Load a training dataset before the testing dataset."
                )

            training_labels = set(json.loads(str(training["labels"])))
            unknown_labels = sorted(set(labels) - training_labels)

            if unknown_labels:
                rendered = ", ".join(unknown_labels)
                raise DatasetUploadError(
                    "The testing dataset contains labels not found in training: "
                    f"{rendered}."
                )

        _write_dataset(dataset_path, content)

        with db.transaction(ADAM_DB_PATH) as connection:
            training = _active_dataset(connection, category, "training")

            if training is None:
                raise DatasetStateError(
                    "The training dataset is no longer available for editing."
                )

            db.execute_on(
                connection,
                """
                UPDATE adam_datasets
                SET status = 'archived', is_active = 0
                WHERE category = ? AND purpose = 'testing' AND is_active = 1
                """,
                (category,),
            )

            db.execute_on(
                connection,
                """
                INSERT INTO adam_datasets (
                    dataset_uid, category, purpose, original_filename,
                    stored_filepath, sha256, records, labels, labels_count
                )
                VALUES (?, ?, 'testing', ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_uid,
                    category,
                    filename,
                    stored_filepath,
                    digest,
                    records,
                    json.dumps(labels, ensure_ascii=False),
                    len(labels),
                ),
            )

            dataset = _pair_response(connection, category)
    except (DatasetUploadError, DatasetStateError):
        dataset_path.unlink(missing_ok=True)
        raise
    except (OSError, db.DatabaseError, RuntimeError) as exc:
        dataset_path.unlink(missing_ok=True)
        raise DatasetStorageError("The testing dataset could not be stored.") from exc

    if dataset is None:
        dataset_path.unlink(missing_ok=True)
        raise DatasetStorageError("The testing dataset could not be registered.")

    return dataset


def store_dataset(
    content: bytes,
    original_filename: str,
    dataset_type: str,
    dataset_category: str,
) -> dict[str, object]:
    """Validate, store, and register one training or testing CSV upload."""
    normalized_type = dataset_type.strip().lower()
    normalized_category = _normalize_category(dataset_category)

    if normalized_type not in ADAM_DATASET_TYPES:
        raise DatasetUploadError("Dataset type must be training or testing.")

    if normalized_type == "training":
        return _store_training_dataset(
            content,
            original_filename,
            normalized_category,
        )

    return _store_testing_dataset(content, original_filename, normalized_category)


def latest_dataset(dataset_category: str) -> dict[str, object] | None:
    """Return the active dataset pair for one category."""
    normalized_category = _normalize_category(dataset_category)

    try:
        with db.transaction(ADAM_DB_PATH) as connection:
            return _pair_response(connection, normalized_category)
    except (OSError, db.DatabaseError, RuntimeError, ValueError) as exc:
        raise DatasetStorageError("The dataset could not be loaded.") from exc


def store_dataset_pair(
    training_content: bytes,
    training_filename: str,
    testing_content: bytes,
    testing_filename: str,
    dataset_category: str,
) -> dict[str, object]:
    """Validate and store the selected training and testing pair together."""
    category = _normalize_category(dataset_category)
    _, training_labels = _inspect_csv(training_content)
    _, testing_labels = _inspect_csv(testing_content)
    unknown_labels = sorted(set(testing_labels) - set(training_labels))

    if unknown_labels:
        raise DatasetUploadError(
            "The testing dataset contains labels not found in training: "
            + ", ".join(unknown_labels) + "."
        )

    store_dataset(training_content, training_filename, "training", category)

    return store_dataset(testing_content, testing_filename, "testing", category)
