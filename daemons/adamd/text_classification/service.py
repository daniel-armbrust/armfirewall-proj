"""Train, evaluate, and publish the ADAM text classifier."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sklearn.metrics import precision_recall_fscore_support
from sklearn.pipeline import Pipeline

from core.constants import (
    ADAM_CHARTS_DIR,
    ADAM_DATASET_DIR,
    ADAM_DATASET_REQUIRED_COLUMNS,
    ADAM_DB_PATH,
    ADAM_DELETE_STAGING_DIR,
    ADAM_MODELS_DIR,
    ADAM_TEXT_CLASSIFIER_DATASET_CATEGORIES,
    ADAM_TEXT_CLASSIFIER_CHART_DPI,
    ADAM_TEXT_CLASSIFIER_CHART_FILENAME_PREFIX,
    ADAM_TEXT_CLASSIFIER_MAX_ITERATIONS,
    ADAM_TEXT_CLASSIFIER_MODEL_PATH,
    ADAM_TEXT_CLASSIFIER_RANDOM_STATE,
    ROOT_DIR,
)

from .evaluation import publish_evaluation_chart
from .cleanup import delete_classifier
from .training import (
    build_classifier,
    publish_model,
    restore_model,
)
from .datasets import (
    load_dataset,
    stored_artifact_path,
    training_datasets,
    training_run,
)
from .persistence import persist_success
from .state import mark_failed, mark_running


def train_text_classifier(training_uid: str, request_uid: str) -> dict[str, Any]:
    """Train, evaluate, publish, and persist one text classifier."""
    training_run = _training_run(training_uid, request_uid)
    
    training_data, testing_data, category = _load_training_data(
        _training_datasets(int(training_run["id"]))
    )

    _validate_training_data(training_data, testing_data)

    training_texts, training_labels = training_data
    testing_texts, testing_labels = testing_data
    classifier = _build_classifier()
    classifier.fit(training_texts, training_labels)
    predictions = classifier.predict(testing_texts)

    model_sha256, rollback_path = _publish_model(classifier)

    metadata = _training_metadata(
        training_run,
        classifier,
        training_data,
        testing_data,
        predictions,
        model_sha256,
    )

    return _publish_and_persist_training(
        int(training_run["id"]),
        str(training_run["training_uid"]),
        category,
        metadata,
        testing_labels,
        predictions,
        rollback_path,
    )


def _load_training_data(
    datasets: list[dict[str, Any]],
) -> tuple[
    tuple[list[str], list[str]],
    tuple[list[str], list[str]],
    str,
]:
    """Load the selected category's training and testing CSV data."""
    datasets_by_purpose = {
        str(dataset["purpose"]): dataset
        for dataset in datasets
    }

    training_dataset = datasets_by_purpose.get("training")
    testing_dataset = datasets_by_purpose.get("testing")

    if training_dataset is None or testing_dataset is None:
        raise ValueError("Training and testing datasets are required.")

    if training_dataset["category"] != testing_dataset["category"]:
        raise ValueError("Training and testing datasets must use the same category.")

    return (
        _load_dataset(training_dataset),
        _load_dataset(testing_dataset),
        str(training_dataset["category"]),
    )


def _validate_training_data(
    training_data: tuple[list[str], list[str]],
    testing_data: tuple[list[str], list[str]],
) -> None:
    """Validate that one dataset pair can train a text classifier."""
    _, training_labels = training_data
    _, testing_labels = testing_data

    if len(set(training_labels)) < 2:
        raise ValueError("Training requires at least two labels.")

    unknown_labels = sorted(set(testing_labels) - set(training_labels))

    if unknown_labels:
        raise ValueError(
            "Testing contains labels not found in training: "
            f"{', '.join(unknown_labels)}."
        )


def _training_metadata(
    training_run: dict[str, Any],
    classifier: Pipeline,
    training_data: tuple[list[str], list[str]],
    testing_data: tuple[list[str], list[str]],
    predictions: Any,
    model_sha256: str,
) -> dict[str, Any]:
    """Build persisted metrics for one trained text classifier."""
    training_texts, training_labels = training_data
    testing_texts, testing_labels = testing_data
    precision, recall, f1_score, _ = precision_recall_fscore_support(
        testing_labels,
        predictions,
        average="macro",
        zero_division=0,
    )

    return {
        "model_id": str(uuid4()),
        "model_file": ADAM_TEXT_CLASSIFIER_MODEL_PATH.name,
        "model_sha256": model_sha256,
        "training_uid": training_run["training_uid"],
        "training_records": len(training_texts),
        "testing_records": len(testing_texts),
        "labels": [str(value) for value in classifier.classes_],
        "training_accuracy": float(classifier.score(training_texts, training_labels)),
        "testing_accuracy": float(classifier.score(testing_texts, testing_labels)),
        "precision_macro": float(precision),
        "recall_macro": float(recall),
        "f1_macro": float(f1_score),
        "parameters": {
            "max_iter": ADAM_TEXT_CLASSIFIER_MAX_ITERATIONS,
            "random_state": ADAM_TEXT_CLASSIFIER_RANDOM_STATE,
        },
    }


def _publish_and_persist_training(
    training_run_id: int,
    training_uid: str,
    category: str,
    metadata: dict[str, Any],
    testing_labels: list[str],
    predictions: Any,
    rollback_path: Path | None,
) -> dict[str, Any]:
    """Publish the single evaluation chart and persist the training result."""
    chart_path: Path | None = None

    try:
        chart_path = _publish_evaluation_chart(
            training_uid,
            metadata,
            testing_labels,
            predictions,
        )
        chart_filepath = str(chart_path.relative_to(ROOT_DIR))
        metadata["evaluation_chart_filepath"] = chart_filepath
        metadata["category_results"] = [
            {
                "category": category,
                "evaluation_chart_filepath": chart_filepath,
            }
        ]
        _persist_success(training_run_id, metadata)
    except Exception:
        _restore_model(rollback_path)
        if chart_path is not None:
            chart_path.unlink(missing_ok=True)
        raise
    else:
        if rollback_path is not None:
            rollback_path.unlink(missing_ok=True)

    return metadata

def delete_text_classifier(training_uid: str) -> dict[str, int]:
    """Delete the active model, charts, datasets, and dependent training runs."""
    return delete_classifier(
        training_uid,
        db_path=ADAM_DB_PATH,
        dataset_dir=ADAM_DATASET_DIR,
        models_dir=ADAM_MODELS_DIR,
        charts_dir=ADAM_CHARTS_DIR,
        staging_dir=ADAM_DELETE_STAGING_DIR,
        normalize_uuid=lambda value, field: _normalize_uuid(value, field_name=field),
        stored_artifact_path=lambda value, root, name: _stored_artifact_path(value, root, name),
    )


def mark_training_running(training_uid: str, request_uid: str) -> None:
    """Mark one queued training run as running."""
    mark_running(
        training_uid,
        request_uid,
        db_path=ADAM_DB_PATH,
        normalize_uuid=lambda value, field: _normalize_uuid(value, field_name=field),
    )


def mark_training_failed(training_uid: str, request_uid: str, message: str,) -> None:
    """Persist a terminal training failure."""
    mark_failed(
        training_uid,
        request_uid,
        message,
        db_path=ADAM_DB_PATH,
        normalize_uuid=lambda value, field: _normalize_uuid(value, field_name=field),
    )


def _normalize_uuid(value: object, *, field_name: str) -> str:
    """Return one canonical UUID value."""
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"The {field_name} must be a valid UUID.") from exc


def _training_run(training_uid: str, request_uid: str) -> dict[str, Any]:
    """Return the running database record for one work request."""
    return training_run(
        training_uid,
        request_uid,
        db_path=ADAM_DB_PATH,
        normalize_uuid=lambda value: _normalize_uuid(value, field_name="training_uid"),
    )


def _training_datasets(training_run_id: int) -> list[dict[str, Any]]:
    """Return compatible datasets associated with one training run."""
    return training_datasets(
        training_run_id,
        db_path=ADAM_DB_PATH,
        compatible_categories=ADAM_TEXT_CLASSIFIER_DATASET_CATEGORIES,
    )


def _stored_artifact_path(stored_filepath: object, artifact_root: Path, artifact_name: str,) -> Path:
    """Resolve one stored artifact inside its configured directory."""
    return stored_artifact_path(
        stored_filepath,
        root_dir=ROOT_DIR,
        artifact_root=artifact_root,
        artifact_name=artifact_name,
    )


def _load_dataset(dataset: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Load one validated UTF-8 text,label CSV."""
    return load_dataset(
        dataset,
        root_dir=ROOT_DIR,
        dataset_dir=ADAM_DATASET_DIR,
        required_columns=ADAM_DATASET_REQUIRED_COLUMNS,
        normalize_uuid=lambda value: _normalize_uuid(value, field_name="dataset_id"),
    )


def _build_classifier() -> Pipeline:
    """Build the initial deterministic text classification pipeline."""
    return build_classifier(
        max_iterations=ADAM_TEXT_CLASSIFIER_MAX_ITERATIONS,
        random_state=ADAM_TEXT_CLASSIFIER_RANDOM_STATE,
    )


def _publish_evaluation_chart(
    training_uid: str,
    metadata: dict[str, Any],
    expected_labels: list[str],
    predicted_labels: Any,
    *,
    chart_suffix: str = "",
) -> Path:
    """Generate and atomically publish one training evaluation chart."""
    chart_identifier = _normalize_uuid(training_uid, field_name="training_uid")
    if chart_suffix:
        chart_identifier = f"{chart_identifier}-{chart_suffix}"

    return publish_evaluation_chart(
        chart_identifier,
        metadata,
        expected_labels,
        predicted_labels,
        charts_dir=ADAM_CHARTS_DIR,
        filename_prefix=ADAM_TEXT_CLASSIFIER_CHART_FILENAME_PREFIX,
        chart_dpi=ADAM_TEXT_CLASSIFIER_CHART_DPI,
    )


def _publish_model(classifier: Any) -> tuple[str, Path | None]:
    """Atomically replace the active model and retain a rollback link."""
    return publish_model(
        classifier,
        models_dir=ADAM_MODELS_DIR,
        model_path=ADAM_TEXT_CLASSIFIER_MODEL_PATH,
    )


def _restore_model(rollback_path: Path | None) -> None:
    """Restore the previous model after a persistence failure."""
    restore_model(ADAM_TEXT_CLASSIFIER_MODEL_PATH, rollback_path)


def _persist_success(training_run_id: int, metadata: dict[str, Any],) -> None:
    """Persist training metrics and activate the new model."""
    persist_success(
        training_run_id,
        metadata,
        db_path=ADAM_DB_PATH,
        root_dir=ROOT_DIR,
        model_path=ADAM_TEXT_CLASSIFIER_MODEL_PATH,
        random_state=ADAM_TEXT_CLASSIFIER_RANDOM_STATE,
    )
