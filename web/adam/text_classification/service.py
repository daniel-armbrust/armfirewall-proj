"""Text-classification result and artifact business rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from core import db
from core.constants import (
    ADAM_DATASET_CATEGORIES,
    ADAM_DB_PATH,
    ADAM_WORK_REQUEST_ACTION,
    ADAM_WORK_REQUEST_CATEGORY,
)
from web.adam.datasets import service as datasets_service
from web.adam.datasets.errors import (
    DatasetStateError,
    DatasetStorageError,
    DatasetUploadError,
)
from web.workrequests import api as workrequests_api

from .errors import TextClassificationStorageError
from . import repository, storage


def prepare_training(
    request_uid: str,
    dataset_category: str,
) -> dict[str, object]:
    """Create a text-classification run for the selected active dataset pair."""
    category = _training_category(dataset_category)

    try:
        with db.transaction(ADAM_DB_PATH) as connection:
            # Fetch the active uploaded training and testing datasets for this category.
            rows = [
                dict(row)
                for row in db.fetch_all_on(
                    connection,
                    """
                    SELECT id, dataset_uid, category, purpose, records, labels
                    FROM adam_datasets
                    WHERE category = ? AND is_active = 1 AND status = 'uploaded'
                    ORDER BY purpose
                    """,
                    (category,),
                )
            ]

            datasets_by_purpose = {
                str(row["purpose"]): row
                for row in rows
            }

            training_dataset = datasets_by_purpose.get("training")
            testing_dataset = datasets_by_purpose.get("testing")

            if training_dataset is None:
                raise DatasetStateError("No uploaded training dataset is available.")

            if testing_dataset is None:
                raise DatasetStateError(
                    "Load both training and testing datasets first."
                )

            training_uid = str(uuid4())
            labels = sorted(json.loads(str(training_dataset["labels"])))

            # Create the queued training run with the selected dataset metadata.
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
                    int(training_dataset["records"]),
                    int(testing_dataset["records"]),
                    json.dumps(labels, ensure_ascii=False),
                    len(labels),
                ),
            )

            training_run_id = int(cursor.lastrowid)

            # Link both selected datasets to this training run for traceability.
            for dataset in (training_dataset, testing_dataset):
                db.execute_on(
                    connection,
                    """
                    INSERT INTO adam_training_run_datasets (training_run_id, dataset_id)
                    VALUES (?, ?)
                    """,
                    (training_run_id, int(dataset["id"])),
                )
    except DatasetStateError:
        raise
    except (OSError, db.DatabaseError, RuntimeError) as exc:
        raise DatasetStorageError(
            "The training request could not be prepared."
        ) from exc

    dataset = datasets_service.latest_dataset(category)

    if dataset is None:
        raise DatasetStorageError("The training request could not be prepared.")

    dataset["training_uid"] = training_uid
    dataset["datasets"] = [
        {
            "dataset_id": row["dataset_uid"],
            "category": row["category"],
            "purpose": row["purpose"],
        }
        for row in (training_dataset, testing_dataset)
    ]

    return dataset


def _training_category(value: str) -> str:
    """Validate the category used to create a text-classification run."""
    category = value.strip().lower()

    if category not in ADAM_DATASET_CATEGORIES:
        raise DatasetUploadError(
            "Dataset category must be Adam Misc, Firewall, Greetings, or NER."
        )

    return category


def queue_training(
    training_content: bytes,
    training_filename: str,
    testing_content: bytes,
    testing_filename: str,
    dataset_category: str,
) -> dict[str, object]:
    """Persist one selected dataset pair and queue its classifier training."""
    datasets_service.store_dataset_pair(
        training_content,
        training_filename,
        testing_content,
        testing_filename,
        dataset_category,
    )

    request_uid = str(uuid4())
    queued = prepare_training(request_uid, dataset_category)

    work_request_id = workrequests_api.queue_work_request(
        action=ADAM_WORK_REQUEST_ACTION,
        category_name=ADAM_WORK_REQUEST_CATEGORY,
        source="gui",
        priority=80,
        request_uid=request_uid,
        allowed_actions=(ADAM_WORK_REQUEST_ACTION,),
        allowed_categories=(ADAM_WORK_REQUEST_CATEGORY,),
        event_message="Queued ADAM intent classifier training.",
        payload={"training_uid": queued["training_uid"]},
    )

    return {
        "message": "Training work request queued successfully.",
        "status": "queue",
        "work_request_id": work_request_id,
        "dataset": queued,
    }


def active_training(dataset_category: str | None = None) -> dict[str, Any] | None:
    """Return the active successful classifier and its selected dataset pair."""
    try:
        training = repository.active_successful_training()

        if training is None:
            return None
        
        datasets = repository.training_datasets(int(training["id"]))
    except db.DatabaseError as exc:
        raise TextClassificationStorageError(
            "The active text classification model could not be read."
        ) from exc

    selected_category = _normalize_category(dataset_category)
    categories = sorted({str(dataset["category"]) for dataset in datasets})

    if selected_category is not None and selected_category not in categories:
        raise TextClassificationStorageError(
            "The selected dataset is not part of the active model."
        )

    chart_filepath = training["evaluation_chart_filepath"]

    if selected_category is not None:
        chart_filepath = next(
            (
                dataset["chart_filepath"]
                for dataset in datasets
                if dataset["category"] == selected_category
                and dataset["purpose"] == "testing"
            ),
            None,
        )

    chart_available = bool(chart_filepath) and storage.chart_path(
        str(chart_filepath)
    ).is_file()

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
        "labels": _json_list(training["labels"]),
        "labels_count": training["labels_count"],
        "metrics": {
            "training_accuracy": training["training_accuracy"],
            "testing_accuracy": training["testing_accuracy"],
            "precision_macro": training["precision_macro"],
            "recall_macro": training["recall_macro"],
            "f1_macro": training["f1_macro"],
        },
        "parameters": _json_object(training["parameters_json"]),
        "random_state": training["random_state"],
        "scikit_learn_version": training["scikit_learn_version"],
        "joblib_version": training["joblib_version"],
        "datasets": [
            {
                "category": dataset["category"],
                "category_name": ADAM_DATASET_CATEGORIES[str(dataset["category"])],
                "purpose": dataset["purpose"],
                "file_name": dataset["original_filename"],
                "records": dataset["records"],
            }
            for dataset in datasets
        ],
        "dataset_categories": [
            {"value": category, "label": ADAM_DATASET_CATEGORIES[category]}
            for category in categories
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
    """Return the validated chart path for an active successful training run."""
    try:
        training = repository.successful_training(training_uid)

        if training is None:
            raise FileNotFoundError("The text classification chart is not available.")

        selected_category = _normalize_category(dataset_category)
        chart_filepath = training["evaluation_chart_filepath"]

        if selected_category is not None:
            chart_filepath = repository.category_chart_filepath(
                int(training["id"]), selected_category
            )
    except db.DatabaseError as exc:
        raise TextClassificationStorageError(
            "The text classification chart could not be read."
        ) from exc

    if not chart_filepath:
        raise FileNotFoundError("The text classification chart is not available.")

    path = storage.chart_path(str(chart_filepath))

    if not path.is_file():
        raise FileNotFoundError("The text classification chart file was not found.")

    return path


def _normalize_category(value: str | None) -> str | None:
    """Return a known category or no category."""
    if value is None or not value.strip():
        return None

    category = value.strip().lower()

    if category not in ADAM_DATASET_CATEGORIES:
        raise TextClassificationStorageError("The selected dataset category is invalid.")

    return category


def _json_list(value: object) -> list[str]:
    """Parse a stored JSON list without exposing malformed database values."""
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _json_object(value: object) -> dict[str, Any]:
    """Parse a stored JSON object without exposing malformed database values."""
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
