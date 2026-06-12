"""Read the active ADAM text classification training result."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core import db
from core.constants import ADAM_CHARTS_DIR, ADAM_DB_PATH, ROOT_DIR


class TextClassificationStorageError(RuntimeError):
    """Raised when active model details cannot be read safely."""


def active_training() -> dict[str, Any] | None:
    """Return the active successful text classifier and its datasets."""
    try:
        training = db.fetch_one(
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

        if training is None:
            return None

        dataset_rows = db.fetch_all(
            """
            SELECT d.category, d.purpose, d.original_filename, d.records
            FROM adam_training_run_datasets AS rd
            JOIN adam_datasets AS d ON d.id = rd.dataset_id
            WHERE rd.training_run_id = ?
            ORDER BY d.category, d.purpose
            """,
            (training["id"],),
            db_path=ADAM_DB_PATH,
        )
    except db.DatabaseError as exc:
        raise TextClassificationStorageError(
            "The active text classification model could not be read."
        ) from exc

    labels = _json_list(training["labels"])
    parameters = _json_object(training["parameters_json"])
    chart_available = False

    if training["evaluation_chart_filepath"]:
        chart_available = _chart_path(training).is_file()

    return {
        "training_uid": training["training_uid"],
        "status": training["status"],
        "completed_at": training["completed_at"],
        "model_id": training["model_id"],
        "model_file": Path(str(training["model_joblib_filepath"])).name,
        "model_sha256": training["model_sha256"],
        "algorithm": training["algorithm"],
        "vectorizer": training["vectorizer"],
        "training_records": training["training_records"],
        "testing_records": training["testing_records"],
        "labels": labels,
        "labels_count": training["labels_count"],
        "metrics": {
            "training_accuracy": training["training_accuracy"],
            "testing_accuracy": training["testing_accuracy"],
            "precision_macro": training["precision_macro"],
            "recall_macro": training["recall_macro"],
            "f1_macro": training["f1_macro"],
        },
        "parameters": parameters,
        "random_state": training["random_state"],
        "scikit_learn_version": training["scikit_learn_version"],
        "joblib_version": training["joblib_version"],
        "datasets": [
            {
                "category": row["category"],
                "purpose": row["purpose"],
                "file_name": row["original_filename"],
                "records": row["records"],
            }
            for row in dataset_rows
        ],
        "chart_url": (
            "/api/adam/text-classification/chart"
            f"?training_uid={training['training_uid']}"
            if chart_available
            else None
        ),
    }


def evaluation_chart(training_uid: str) -> Path:
    """Return the validated chart path for the active training run."""
    try:
        training = db.fetch_one(
            """
            SELECT training_uid, evaluation_chart_filepath
            FROM adam_training_runs
            WHERE training_uid = ? AND is_active = 1 AND status = 'success'
            """,
            (training_uid,),
            db_path=ADAM_DB_PATH,
        )
    except db.DatabaseError as exc:
        raise TextClassificationStorageError(
            "The text classification chart could not be read."
        ) from exc

    if training is None or not training["evaluation_chart_filepath"]:
        raise FileNotFoundError("The text classification chart is not available.")

    chart_path = _chart_path(training)

    if not chart_path.is_file():
        raise FileNotFoundError("The text classification chart file was not found.")

    return chart_path


def _chart_path(training: dict[str, Any]) -> Path:
    """Resolve a stored chart path inside the configured ADAM chart directory."""
    chart_path = (ROOT_DIR / str(training["evaluation_chart_filepath"])).resolve()

    if not chart_path.is_relative_to(ADAM_CHARTS_DIR.resolve()):
        raise TextClassificationStorageError(
            "The text classification chart path is invalid."
        )

    return chart_path


def _json_list(value: object) -> list[str]:
    """Parse a stored JSON list without leaking malformed database values."""
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return []

    if not isinstance(parsed, list):
        return []

    return [str(item) for item in parsed]


def _json_object(value: object) -> dict[str, Any]:
    """Parse a stored JSON object without leaking malformed database values."""
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return {}

    return parsed if isinstance(parsed, dict) else {}
