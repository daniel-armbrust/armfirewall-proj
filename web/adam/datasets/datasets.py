"""Validate, store, and query datasets uploaded through the ADAM web interface."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from core import db
from core.constants import (
    ADAM_DATASET_CATEGORIES,
    ADAM_DATASET_DIR,
    ADAM_DATASET_MAX_BYTES,
    ADAM_DATASET_MAX_ROWS,
    ADAM_DATASET_REQUIRED_COLUMNS,
    ADAM_DATASET_TYPES,
    ADAM_DB_PATH,
)


class DatasetUploadError(ValueError):
    """Represent an invalid ADAM dataset upload."""


class DatasetStorageError(RuntimeError):
    """Represent an ADAM dataset persistence failure."""


class DatasetStateError(RuntimeError):
    """Represent an invalid transition in the ADAM dataset workflow."""


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

    if len(labels) < 2:
        raise DatasetUploadError("The dataset must contain at least two labels.")

    return records, sorted(labels)


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


def _active_dataset(
    connection: db.Connection,
    category: str,
    purpose: str,
) -> dict[str, object] | None:
    """Return the active dataset for one category and purpose."""
    row = db.fetch_one_on(
        connection,
        """
        SELECT id, dataset_uid, category, purpose, original_filename,
               stored_filepath, chart_filepath, sha256, records,
               labels, labels_count, status, created_at, updated_at
        FROM adam_datasets
        WHERE category = ? AND purpose = ? AND is_active = 1
        LIMIT 1
        """,
        (category, purpose),
    )

    return dict(row) if row else None


def _latest_run_for_pair(
    connection: db.Connection,
    training_id: int,
    testing_id: int,
) -> dict[str, object] | None:
    """Return the latest training run that used both datasets in a pair."""
    row = db.fetch_one_on(
        connection,
        """
        SELECT r.id, r.training_uid, r.work_request_uid, r.status,
               r.created_at, r.updated_at
        FROM adam_training_runs AS r
        WHERE EXISTS (
             SELECT 1 FROM adam_training_run_datasets AS rd
             WHERE rd.training_run_id = r.id AND rd.dataset_id = ?
        )
          AND EXISTS (
             SELECT 1 FROM adam_training_run_datasets AS rd
             WHERE rd.training_run_id = r.id AND rd.dataset_id = ?
        )
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (training_id, testing_id),
    )

    return dict(row) if row else None


def _dataset_summary(row: dict[str, object]) -> dict[str, object]:
    """Return the public summary for one uploaded CSV."""
    return {
        "dataset_id": row["dataset_uid"],
        "file_name": row["original_filename"],
        "rows": row["records"],
        "labels": json.loads(str(row["labels"])),
        "labels_count": row["labels_count"],
        "sha256": row["sha256"],
        "purpose": row["purpose"],
    }


def _pair_response(
    connection: db.Connection,
    category: str,
    *,
    run_id: int | None = None,
) -> dict[str, object] | None:
    """Return the active dataset pair expected by the ADAM page."""
    training = _active_dataset(connection, category, "training")
    testing = _active_dataset(connection, category, "testing")

    if training is None:
        return None

    run = None

    if run_id is not None:
        selected = db.fetch_one_on(
            connection,
            """
            SELECT id, training_uid, work_request_uid, status,
                   created_at, updated_at
            FROM adam_training_runs
            WHERE id = ?
            """,
            (run_id,),
        )

        run = dict(selected) if selected else None
    elif testing is not None:
        run = _latest_run_for_pair(
            connection,
            int(training["id"]),
            int(testing["id"]),
        )

    training_summary = _dataset_summary(training)
    testing_summary = _dataset_summary(testing) if testing else None

    updated_at = max(
        str(training["updated_at"]),
        str(testing["updated_at"]) if testing else "",
        str(run["updated_at"]) if run else "",
    )

    return {
        "dataset_category": category,
        "dataset_category_name": ADAM_DATASET_CATEGORIES[category],
        "dataset_id": training["dataset_uid"],
        "training_uid": run["training_uid"] if run else None,
        "work_request_uid": run["work_request_uid"] if run else None,
        "file_name": training["original_filename"],
        "rows": training["records"],
        "intentions": training["labels_count"],
        "labels": training_summary["labels"],
        "sha256": training["sha256"],
        "status": run["status"] if run else "uploaded",
        "training": training_summary,
        "testing": testing_summary,
        "updated_at": updated_at.replace(" ", "T") + "Z",
    }


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
    dataset_category: str = "firewall",
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


def latest_dataset(dataset_category: str = "firewall") -> dict[str, object] | None:
    """Return the active dataset pair for one category."""
    normalized_category = _normalize_category(dataset_category)

    try:
        with db.transaction(ADAM_DB_PATH) as connection:
            return _pair_response(connection, normalized_category)
    except (OSError, db.DatabaseError, RuntimeError, ValueError) as exc:
        raise DatasetStorageError("The dataset could not be loaded.") from exc


def prepare_training(
    request_uid: str,
    dataset_category: str = "firewall",
) -> dict[str, object]:
    """Create one run using every complete active dataset category."""
    selected_category = _normalize_category(dataset_category)

    try:
        with db.transaction(ADAM_DB_PATH) as connection:
            rows = db.fetch_all_on(
                connection,
                """
                SELECT id, dataset_uid, category, purpose, original_filename,
                       stored_filepath, sha256, records, labels, labels_count,
                       status, created_at, updated_at
                FROM adam_datasets
                WHERE is_active = 1 AND status = 'uploaded'
                ORDER BY category, purpose
                """,
            )

            grouped: dict[str, dict[str, dict[str, object]]] = {}

            for raw_row in rows:
                row = dict(raw_row)
                grouped.setdefault(str(row["category"]), {})[str(row["purpose"])] = row

            selected = grouped.get(selected_category, {})

            if "training" not in selected:
                raise DatasetStateError("No uploaded training dataset is available.")

            if "testing" not in selected:
                raise DatasetStateError("Load both training and testing datasets first.")

            complete = [
                pair
                for pair in grouped.values()
                if "training" in pair and "testing" in pair
            ]

            selected_rows = [
                dataset
                for pair in complete
                for dataset in (pair["training"], pair["testing"])
            ]

            training_records = sum(
                int(pair["training"]["records"]) for pair in complete
            )

            testing_records = sum(
                int(pair["testing"]["records"]) for pair in complete
            )

            labels = sorted(
                {
                    label
                    for pair in complete
                    for label in json.loads(str(pair["training"]["labels"]))
                }
            )

            training_uid = str(uuid4())

            cursor = db.execute_on(
                connection,
                """
                INSERT INTO adam_training_runs (
                    training_uid, work_request_uid, status,
                    training_records, testing_records, labels, labels_count
                )
                VALUES (?, ?, 'queue', ?, ?, ?, ?)
                """,
                (
                    training_uid,
                    request_uid,
                    training_records,
                    testing_records,
                    json.dumps(labels, ensure_ascii=False),
                    len(labels),
                ),
            )

            run_id = int(cursor.lastrowid)

            for dataset in selected_rows:
                db.execute_on(
                    connection,
                    """
                    INSERT INTO adam_training_run_datasets (training_run_id, dataset_id)
                    VALUES (?, ?)
                    """,
                    (run_id, int(dataset["id"])),
                )

            queued = _pair_response(
                connection,
                selected_category,
                run_id=run_id,
            )
    except DatasetStateError:
        raise
    except (OSError, db.DatabaseError, RuntimeError) as exc:
        raise DatasetStorageError("The training request could not be prepared.") from exc

    if queued is None:
        raise DatasetStorageError("The training request could not be prepared.")

    queued["training_uid"] = training_uid

    queued["datasets"] = [
        {
            "dataset_id": dataset["dataset_uid"],
            "category": dataset["category"],
            "purpose": dataset["purpose"],
        }
        for dataset in selected_rows
    ]
    
    return queued


def restore_uploaded(request_uid: str) -> None:
    """Remove a queued run when work request creation fails."""
    try:
        db.execute(
            """
            DELETE FROM adam_training_runs
            WHERE work_request_uid = ? AND status = 'queue'
            """,
            (request_uid,),
            db_path=ADAM_DB_PATH,
        )
    except (OSError, db.DatabaseError, RuntimeError) as exc:
        raise DatasetStorageError("The dataset state could not be restored.") from exc
