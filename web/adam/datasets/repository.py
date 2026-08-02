"""SQLite queries and response mapping for ADAM datasets."""

from __future__ import annotations

import json

from core import db
from core.constants import ADAM_DATASET_CATEGORIES, ADAM_DB_PATH


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
