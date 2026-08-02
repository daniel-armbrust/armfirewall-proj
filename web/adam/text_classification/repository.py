"""SQLite queries for ADAM text-classification training results."""

from __future__ import annotations

from typing import Any

from core import db
from core.constants import ADAM_DB_PATH


def active_successful_training() -> dict[str, Any] | None:
    """Return the active successful training run, if one exists."""
    row = db.fetch_one(
        """
        SELECT id, training_uid, status, completed_at, model_id,
               model_joblib_filepath, evaluation_chart_filepath,
               model_sha256, training_records, testing_records,
               labels, labels_count, training_accuracy, testing_accuracy,
               precision_macro, recall_macro, f1_macro, algorithm,
               vectorizer, parameters_json, random_state,
               scikit_learn_version, joblib_version
        FROM adam_training_runs
        WHERE is_active = 1 AND status = 'success'
        LIMIT 1
        """,
        db_path=ADAM_DB_PATH,
    )

    return dict(row) if row else None


def successful_training(training_uid: str) -> dict[str, Any] | None:
    """Return one active successful training run by its public identifier."""
    row = db.fetch_one(
        """
        SELECT id, training_uid, evaluation_chart_filepath
        FROM adam_training_runs
        WHERE training_uid = ? AND is_active = 1 AND status = 'success'
        """,
        (training_uid,),
        db_path=ADAM_DB_PATH,
    )

    return dict(row) if row else None


def training_datasets(training_run_id: int) -> list[dict[str, Any]]:
    """Return the datasets associated with one training run."""
    rows = db.fetch_all(
        """
        SELECT d.category, d.purpose, d.original_filename, d.records,
               d.chart_filepath
        FROM adam_training_run_datasets AS rd
        JOIN adam_datasets AS d ON d.id = rd.dataset_id
        WHERE rd.training_run_id = ?
        ORDER BY d.category, d.purpose
        """,
        (training_run_id,),
        db_path=ADAM_DB_PATH,
    )

    return [dict(row) for row in rows]


def category_chart_filepath(training_run_id: int, category: str) -> str | None:
    """Return the testing chart recorded for one category in a training run."""
    row = db.fetch_one(
        """
        SELECT d.chart_filepath
        FROM adam_training_run_datasets AS rd
        JOIN adam_datasets AS d ON d.id = rd.dataset_id
        WHERE rd.training_run_id = ?
          AND d.category = ?
          AND d.purpose = 'testing'
        """,
        (training_run_id, category),
        db_path=ADAM_DB_PATH,
    )
    
    return str(row["chart_filepath"]) if row and row["chart_filepath"] else None
