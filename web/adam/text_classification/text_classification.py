"""Read the active ADAM text classification training result."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import joblib
from sklearn.metrics import precision_recall_fscore_support

from core import db
from core.constants import (
    ADAM_CHARTS_DIR,
    ADAM_DATASET_CATEGORIES,
    ADAM_DATASET_DIR,
    ADAM_DATASET_REQUIRED_COLUMNS,
    ADAM_DB_PATH,
    ADAM_MODELS_DIR,
    ROOT_DIR,
)


class TextClassificationStorageError(RuntimeError):
    """Raised when active model details cannot be read safely."""


def active_training(dataset_category: str | None = None) -> dict[str, Any] | None:
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
            SELECT d.category, d.purpose, d.original_filename, d.records,
                   d.stored_filepath, d.chart_filepath
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

    selected_category = _normalize_category(dataset_category)
    datasets = [dict(row) for row in dataset_rows]
    if selected_category is not None:
        selected_datasets = [
            dataset for dataset in datasets
            if dataset["category"] == selected_category
        ]
        if len(selected_datasets) != 2:
            raise TextClassificationStorageError(
                "The selected dataset is not part of the active model."
            )
        evaluation = _evaluate_category(training, selected_datasets)
        labels = evaluation["labels"]
        metrics = evaluation["metrics"]
        training_records = evaluation["training_records"]
        testing_records = evaluation["testing_records"]
        chart_filepath = next(
            (
                dataset["chart_filepath"]
                for dataset in selected_datasets
                if dataset["purpose"] == "testing"
            ),
            None,
        )
    else:
        labels = _json_list(training["labels"])
        metrics = {
            "training_accuracy": training["training_accuracy"],
            "testing_accuracy": training["testing_accuracy"],
            "precision_macro": training["precision_macro"],
            "recall_macro": training["recall_macro"],
            "f1_macro": training["f1_macro"],
        }
        training_records = training["training_records"]
        testing_records = training["testing_records"]
        chart_filepath = training["evaluation_chart_filepath"]

    parameters = _json_object(training["parameters_json"])
    chart_available = _chart_path_value(chart_filepath).is_file() if chart_filepath else False

    return {
        "training_uid": training["training_uid"],
        "status": training["status"],
        "completed_at": training["completed_at"],
        "model_id": training["model_id"],
        "model_file": Path(str(training["model_joblib_filepath"])).name,
        "model_sha256": training["model_sha256"],
        "algorithm": training["algorithm"],
        "vectorizer": training["vectorizer"],
        "training_records": training_records,
        "testing_records": testing_records,
        "labels": labels,
        "labels_count": training["labels_count"],
        "metrics": metrics,
        "parameters": parameters,
        "random_state": training["random_state"],
        "scikit_learn_version": training["scikit_learn_version"],
        "joblib_version": training["joblib_version"],
        "datasets": [
            {
                "category": row["category"],
                "category_name": ADAM_DATASET_CATEGORIES[row["category"]],
                "purpose": row["purpose"],
                "file_name": row["original_filename"],
                "records": row["records"],
            }
            for row in datasets
        ],
        "dataset_categories": [
            {"value": category, "label": ADAM_DATASET_CATEGORIES[category]}
            for category in sorted({str(row["category"]) for row in datasets})
        ],
        "selected_category": selected_category,
        "chart_url": (
            "/api/adam/text-classification/chart"
            f"?training_uid={training['training_uid']}"
            + (f"&dataset_category={selected_category}" if selected_category else "")
            if chart_available
            else None
        ),
    }


def evaluation_chart(training_uid: str, dataset_category: str | None = None) -> Path:
    """Return the validated chart path for the active training run."""
    try:
        training = db.fetch_one(
            """
            SELECT id, training_uid, evaluation_chart_filepath
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

    if training is None:
        raise FileNotFoundError("The text classification chart is not available.")

    selected_category = _normalize_category(dataset_category)
    chart_filepath = training["evaluation_chart_filepath"]
    if selected_category is not None:
        dataset = db.fetch_one(
            """
            SELECT d.chart_filepath
            FROM adam_training_run_datasets AS rd
            JOIN adam_datasets AS d ON d.id = rd.dataset_id
            WHERE rd.training_run_id = ?
              AND d.category = ?
              AND d.purpose = 'testing'
            """,
            (training["id"], selected_category),
            db_path=ADAM_DB_PATH,
        )
        chart_filepath = dataset["chart_filepath"] if dataset else None

    if not chart_filepath:
        raise FileNotFoundError("The text classification chart is not available.")

    chart_path = _chart_path_value(chart_filepath)

    if not chart_path.is_file():
        raise FileNotFoundError("The text classification chart file was not found.")

    return chart_path


def _chart_path(training: dict[str, Any]) -> Path:
    """Resolve a stored chart path inside the configured ADAM chart directory."""
    return _chart_path_value(training["evaluation_chart_filepath"])


def _chart_path_value(chart_filepath: object) -> Path:
    """Resolve a stored evaluation chart path inside the ADAM chart directory."""
    chart_path = (ROOT_DIR / str(chart_filepath)).resolve()

    if not chart_path.is_relative_to(ADAM_CHARTS_DIR.resolve()):
        raise TextClassificationStorageError(
            "The text classification chart path is invalid."
        )

    return chart_path


def _normalize_category(value: str | None) -> str | None:
    """Return a known category or no category for all-dataset metrics."""
    if value is None or not value.strip():
        return None

    category = value.strip().lower()
    if category not in ADAM_DATASET_CATEGORIES:
        raise TextClassificationStorageError("The selected dataset category is invalid.")
    return category


def _evaluate_category(
    training: dict[str, Any], datasets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate the active shared model against one category's dataset pair."""
    dataset_by_purpose = {str(dataset["purpose"]): dataset for dataset in datasets}
    training_texts, training_labels = _load_dataset(dataset_by_purpose["training"])
    testing_texts, testing_labels = _load_dataset(dataset_by_purpose["testing"])
    model_path = (ROOT_DIR / str(training["model_joblib_filepath"])).resolve()
    if not model_path.is_relative_to(ADAM_MODELS_DIR.resolve()) or not model_path.is_file():
        raise TextClassificationStorageError("The active model file is not available.")

    try:
        classifier = joblib.load(model_path)
        predictions = classifier.predict(testing_texts)
        precision, recall, f1_score, _ = precision_recall_fscore_support(
            testing_labels, predictions, average="macro", zero_division=0
        )
    except Exception as exc:
        raise TextClassificationStorageError(
            "The selected dataset metrics could not be evaluated."
        ) from exc

    return {
        "training_records": len(training_texts),
        "testing_records": len(testing_texts),
        "labels": sorted(
            set(training_labels) | set(testing_labels) | {str(value) for value in predictions}
        ),
        "metrics": {
            "training_accuracy": float(classifier.score(training_texts, training_labels)),
            "testing_accuracy": float(classifier.score(testing_texts, testing_labels)),
            "precision_macro": float(precision),
            "recall_macro": float(recall),
            "f1_macro": float(f1_score),
        },
    }


def _load_dataset(dataset: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Read a stored category dataset after constraining its filesystem path."""
    dataset_path = (ROOT_DIR / str(dataset["stored_filepath"])).resolve()
    if not dataset_path.is_relative_to(ADAM_DATASET_DIR.resolve()) or not dataset_path.is_file():
        raise TextClassificationStorageError("The selected dataset file is not available.")

    with dataset_path.open("r", encoding="utf-8-sig", newline="") as dataset_file:
        reader = csv.DictReader(dataset_file)
        if tuple(reader.fieldnames or ()) != ADAM_DATASET_REQUIRED_COLUMNS:
            raise TextClassificationStorageError("The selected dataset CSV is invalid.")
        rows = list(reader)

    return [str(row["text"]) for row in rows], [str(row["label"]) for row in rows]


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
