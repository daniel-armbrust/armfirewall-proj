"""Train, evaluate, and publish the ADAM text classifier."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import joblib
import matplotlib
import sklearn
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.pipeline import Pipeline

from core import db
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


def train_text_classifier(training_uid: str, request_uid: str) -> dict[str, Any]:
    """Train, evaluate, publish, and persist one text classifier."""
    training_run = _training_run(training_uid, request_uid)
    datasets = _training_datasets(int(training_run["id"]))
    training_texts: list[str] = []
    training_labels: list[str] = []
    testing_texts: list[str] = []
    testing_labels: list[str] = []

    for dataset in datasets:
        texts, labels = _load_dataset(dataset)

        if dataset["purpose"] == "training":
            training_texts.extend(texts)
            training_labels.extend(labels)
        elif dataset["purpose"] == "testing":
            testing_texts.extend(texts)
            testing_labels.extend(labels)

    if not training_texts or not testing_texts:
        raise ValueError("Training and testing datasets are required.")

    if len(set(training_labels)) < 2:
        raise ValueError("Training requires at least two labels.")

    unknown_labels = sorted(set(testing_labels) - set(training_labels))

    if unknown_labels:
        rendered = ", ".join(unknown_labels)
        raise ValueError(
            f"Testing contains labels not found in training: {rendered}."
        )

    classifier = _build_classifier()
    classifier.fit(training_texts, training_labels)
    predictions = classifier.predict(testing_texts)
    precision, recall, f1_score, _ = precision_recall_fscore_support(
        testing_labels,
        predictions,
        average="macro",
        zero_division=0,
    )

    model_sha256, rollback_path = _publish_model(classifier)
    labels = [str(value) for value in classifier.classes_]

    metadata = {
        "model_id": str(uuid4()),
        "model_file": ADAM_TEXT_CLASSIFIER_MODEL_PATH.name,
        "model_sha256": model_sha256,
        "training_uid": training_run["training_uid"],
        "training_records": len(training_texts),
        "testing_records": len(testing_texts),
        "labels": labels,
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
    evaluation_chart_path: Path | None = None

    try:
        evaluation_chart_path = _publish_evaluation_chart(
            str(training_run["training_uid"]),
            metadata,
            testing_labels,
            predictions,
        )
        metadata["evaluation_chart_filepath"] = str(
            evaluation_chart_path.relative_to(ROOT_DIR)
        )
        _persist_success(int(training_run["id"]), metadata)
    except Exception:
        _restore_model(rollback_path)

        if evaluation_chart_path is not None:
            evaluation_chart_path.unlink(missing_ok=True)
        raise
    else:
        if rollback_path is not None:
            rollback_path.unlink(missing_ok=True)

    return metadata


def delete_text_classifier(training_uid: str) -> dict[str, int]:
    """Delete the active model, charts, datasets, and dependent training runs."""
    normalized_training_uid = _normalize_uuid(
        training_uid,
        field_name="training_uid",
    )
    training_run = db.fetch_one(
        """
        SELECT id, model_joblib_filepath, evaluation_chart_filepath
        FROM adam_training_runs
        WHERE training_uid = ? AND is_active = 1 AND status = 'success'
        """,
        (normalized_training_uid,),
        db_path=ADAM_DB_PATH,
    )

    if training_run is None:
        raise ValueError("The active ADAM text classifier was not found.")

    datasets = db.fetch_all(
        """
        SELECT d.id, d.dataset_uid, d.stored_filepath
        FROM adam_training_run_datasets AS rd
        JOIN adam_datasets AS d ON d.id = rd.dataset_id
        WHERE rd.training_run_id = ?
        ORDER BY d.id
        """,
        (training_run["id"],),
        db_path=ADAM_DB_PATH,
    )
    dataset_ids = [int(dataset["id"]) for dataset in datasets]

    if dataset_ids:
        dataset_placeholders = ", ".join("?" for _ in dataset_ids)
        affected_runs = db.fetch_all(
            f"""
            SELECT DISTINCT r.id, r.evaluation_chart_filepath
            FROM adam_training_runs AS r
            JOIN adam_training_run_datasets AS rd
              ON rd.training_run_id = r.id
            WHERE rd.dataset_id IN ({dataset_placeholders})
            """,
            tuple(dataset_ids),
            db_path=ADAM_DB_PATH,
        )
    else:
        affected_runs = []

    affected_run_ids = {int(run["id"]) for run in affected_runs}
    affected_run_ids.add(int(training_run["id"]))
    artifact_paths: set[Path] = set()

    if training_run["model_joblib_filepath"]:
        artifact_paths.add(
            _stored_artifact_path(
                training_run["model_joblib_filepath"],
                ADAM_MODELS_DIR,
                "model",
            )
        )

    if training_run["evaluation_chart_filepath"]:
        artifact_paths.add(
            _stored_artifact_path(
                training_run["evaluation_chart_filepath"],
                ADAM_CHARTS_DIR,
                "chart",
            )
        )

    for run in affected_runs:
        if run["evaluation_chart_filepath"]:
            artifact_paths.add(
                _stored_artifact_path(
                    run["evaluation_chart_filepath"],
                    ADAM_CHARTS_DIR,
                    "chart",
                )
            )

    for dataset in datasets:
        _normalize_uuid(dataset["dataset_uid"], field_name="dataset_id")
        artifact_paths.add(
            _stored_artifact_path(
                dataset["stored_filepath"],
                ADAM_DATASET_DIR,
                "dataset",
            )
        )

    ADAM_DELETE_STAGING_DIR.mkdir(parents=True, exist_ok=True, mode=0o750)
    staging_path = Path(
        tempfile.mkdtemp(prefix=".delete-", dir=ADAM_DELETE_STAGING_DIR)
    )
    staged_files: list[tuple[Path, Path]] = []

    try:
        for index, artifact_path in enumerate(sorted(artifact_paths)):
            if not artifact_path.exists():
                continue

            if not artifact_path.is_file():
                raise ValueError(
                    f"The ADAM {artifact_path.name} artifact is not a regular file."
                )

            staged_path = staging_path / f"{index}-{artifact_path.name}"
            os.replace(artifact_path, staged_path)
            staged_files.append((artifact_path, staged_path))

        run_ids = sorted(affected_run_ids)
        run_placeholders = ", ".join("?" for _ in run_ids)

        with db.transaction(ADAM_DB_PATH) as connection:
            db.execute_on(
                connection,
                f"""
                DELETE FROM adam_training_run_datasets
                WHERE training_run_id IN ({run_placeholders})
                """,
                tuple(run_ids),
            )
            db.execute_on(
                connection,
                f"""
                DELETE FROM adam_training_runs
                WHERE id IN ({run_placeholders})
                """,
                tuple(run_ids),
            )

            if dataset_ids:
                dataset_placeholders = ", ".join("?" for _ in dataset_ids)
                db.execute_on(
                    connection,
                    f"""
                    DELETE FROM adam_datasets
                    WHERE id IN ({dataset_placeholders})
                    """,
                    tuple(dataset_ids),
                )
    except Exception:
        for artifact_path, staged_path in reversed(staged_files):
            if staged_path.exists():
                os.replace(staged_path, artifact_path)

        staging_path.rmdir()
        raise

    for _, staged_path in staged_files:
        staged_path.unlink(missing_ok=True)

    staging_path.rmdir()
    return {
        "training_runs": len(affected_run_ids),
        "datasets": len(dataset_ids),
        "files": len(staged_files),
    }


def mark_training_running(training_uid: str, request_uid: str) -> None:
    """Mark one queued training run as running."""
    updated = db.execute(
        """
        UPDATE adam_training_runs
        SET status = 'running', started_at = CURRENT_TIMESTAMP,
            completed_at = NULL, error_message = NULL
        WHERE training_uid = ? AND work_request_uid = ? AND status = 'queue'
        """,
        (
            _normalize_uuid(training_uid, field_name="training_uid"),
            _normalize_uuid(request_uid, field_name="request_uid"),
        ),
        db_path=ADAM_DB_PATH,
    )

    if updated != 1:
        raise ValueError("The ADAM training run is not queued.")


def mark_training_failed(
    training_uid: str,
    request_uid: str,
    message: str,
) -> None:
    """Persist a terminal training failure."""
    db.execute(
        """
        UPDATE adam_training_runs
        SET status = 'failed',
            started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
            completed_at = CURRENT_TIMESTAMP,
            error_message = ?, is_active = 0
        WHERE training_uid = ? AND work_request_uid = ?
          AND status IN ('queue', 'running')
        """,
        (
            message[:2000],
            _normalize_uuid(training_uid, field_name="training_uid"),
            _normalize_uuid(request_uid, field_name="request_uid"),
        ),
        db_path=ADAM_DB_PATH,
    )


def _normalize_uuid(value: object, *, field_name: str) -> str:
    """Return one canonical UUID value."""
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"The {field_name} must be a valid UUID.") from exc


def _training_run(training_uid: str, request_uid: str) -> dict[str, Any]:
    """Return the running database record for one work request."""
    row = db.fetch_one(
        """
        SELECT id, training_uid, work_request_uid, status
        FROM adam_training_runs
        WHERE training_uid = ? AND work_request_uid = ? AND status = 'running'
        """,
        (
            _normalize_uuid(training_uid, field_name="training_uid"),
            _normalize_uuid(request_uid, field_name="request_uid"),
        ),
        db_path=ADAM_DB_PATH,
    )

    if row is None:
        raise ValueError("The running ADAM training run was not found.")

    return row


def _training_datasets(training_run_id: int) -> list[dict[str, Any]]:
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
        db_path=ADAM_DB_PATH,
    )

    compatible = [
        row
        for row in rows
        if str(row["category"]) in ADAM_TEXT_CLASSIFIER_DATASET_CATEGORIES
    ]

    if not compatible:
        raise ValueError("No compatible datasets are associated with this training run.")

    return compatible


def _dataset_path(dataset: dict[str, Any]) -> Path:
    """Resolve and validate one stored dataset path."""
    _normalize_uuid(dataset["dataset_uid"], field_name="dataset_id")
    path = (ROOT_DIR / str(dataset["stored_filepath"])).resolve()
    dataset_root = ADAM_DATASET_DIR.resolve()

    if not path.is_relative_to(dataset_root):
        raise ValueError("The dataset path is outside the ADAM dataset directory.")

    if not path.is_file():
        raise FileNotFoundError(f"The dataset file was not found: {path.name}")

    return path


def _stored_artifact_path(
    stored_filepath: object,
    artifact_root: Path,
    artifact_name: str,
) -> Path:
    """Resolve one stored artifact inside its configured directory."""
    path = (ROOT_DIR / str(stored_filepath)).resolve()

    if not path.is_relative_to(artifact_root.resolve()):
        raise ValueError(f"The ADAM {artifact_name} path is invalid.")

    return path


def _load_dataset(dataset: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Load one validated UTF-8 text,label CSV."""
    texts: list[str] = []
    labels: list[str] = []

    with _dataset_path(dataset).open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as dataset_file:
        reader = csv.DictReader(dataset_file)

        if tuple(reader.fieldnames or ()) != ADAM_DATASET_REQUIRED_COLUMNS:
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


def _build_classifier() -> Pipeline:
    """Build the initial deterministic text classification pipeline."""
    return Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    sublinear_tf=True,
                ),
            ),
            (
                "classifier",
                LogisticRegression(
                    max_iter=ADAM_TEXT_CLASSIFIER_MAX_ITERATIONS,
                    random_state=ADAM_TEXT_CLASSIFIER_RANDOM_STATE,
                ),
            ),
        ]
    )


def _file_sha256(path: Path) -> str:
    """Return the SHA-256 digest for one file."""
    digest = hashlib.sha256()

    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _publish_evaluation_chart(
    training_uid: str,
    metadata: dict[str, Any],
    expected_labels: list[str],
    predicted_labels: Any,
) -> Path:
    """Generate and atomically publish one training evaluation chart."""
    normalized_training_uid = _normalize_uuid(
        training_uid,
        field_name="training_uid",
    )
    labels = [str(value) for value in metadata["labels"]]
    matrix = confusion_matrix(
        expected_labels,
        predicted_labels,
        labels=labels,
    )
    metric_names = [
        "Training accuracy",
        "Testing accuracy",
        "Precision macro",
        "Recall macro",
        "F1 macro",
    ]
    metric_values = [
        metadata["training_accuracy"],
        metadata["testing_accuracy"],
        metadata["precision_macro"],
        metadata["recall_macro"],
        metadata["f1_macro"],
    ]
    chart_path = ADAM_CHARTS_DIR / (
        f"{ADAM_TEXT_CLASSIFIER_CHART_FILENAME_PREFIX}_{normalized_training_uid}.png"
    )
    ADAM_CHARTS_DIR.mkdir(parents=True, exist_ok=True, mode=0o750)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=ADAM_CHARTS_DIR,
        prefix=".text_classifier-",
        suffix=".png.tmp",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    figure = None

    try:
        figure_width = min(18.0, max(11.0, 8.0 + len(labels) * 0.45))
        figure_height = min(12.0, max(5.2, 4.0 + len(labels) * 0.35))
        figure, axes = plt.subplots(
            1,
            2,
            figsize=(figure_width, figure_height),
            gridspec_kw={"width_ratios": (1.0, 1.35)},
        )
        metric_axis, matrix_axis = axes
        bars = metric_axis.barh(
            metric_names,
            metric_values,
            color=["#30d878", "#15c5a5", "#40a9ff", "#ffb84d", "#d978ff"],
        )
        metric_axis.set_xlim(0.0, 1.0)
        metric_axis.set_xlabel("Score")
        metric_axis.set_title("Classifier metrics")
        metric_axis.grid(axis="x", alpha=0.2)
        metric_axis.invert_yaxis()

        for bar, value in zip(bars, metric_values, strict=True):
            metric_axis.text(
                min(float(value) + 0.02, 0.98),
                bar.get_y() + bar.get_height() / 2,
                f"{float(value):.1%}",
                va="center",
                ha="left" if float(value) <= 0.9 else "right",
                fontsize=9,
            )

        image = matrix_axis.imshow(matrix, interpolation="nearest", cmap="Greens")
        matrix_axis.set_title("Testing confusion matrix")
        matrix_axis.set_xlabel("Predicted label")
        matrix_axis.set_ylabel("Expected label")
        matrix_axis.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
        matrix_axis.set_yticks(range(len(labels)), labels)
        annotation_size = max(5, 10 - len(labels) // 4)
        threshold = float(matrix.max()) / 2 if matrix.size else 0.0

        for row_index in range(matrix.shape[0]):
            for column_index in range(matrix.shape[1]):
                value = int(matrix[row_index, column_index])
                matrix_axis.text(
                    column_index,
                    row_index,
                    str(value),
                    ha="center",
                    va="center",
                    color="white" if value > threshold else "black",
                    fontsize=annotation_size,
                )

        figure.colorbar(image, ax=matrix_axis, fraction=0.046, pad=0.04)
        figure.suptitle("Adam - Text Classifier Evaluation", fontweight="bold")
        figure.tight_layout()
        figure.savefig(
            temporary_path,
            format="png",
            dpi=ADAM_TEXT_CLASSIFIER_CHART_DPI,
            bbox_inches="tight",
        )
        os.chmod(temporary_path, 0o640)

        with temporary_path.open("rb") as chart_file:
            os.fsync(chart_file.fileno())

        os.replace(temporary_path, chart_path)
        return chart_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        if figure is not None:
            plt.close(figure)


def _publish_model(classifier: Pipeline) -> tuple[str, Path | None]:
    """Atomically replace the active model and retain a rollback link."""
    ADAM_MODELS_DIR.mkdir(parents=True, exist_ok=True, mode=0o750)

    descriptor, temporary_name = tempfile.mkstemp(
        dir=ADAM_MODELS_DIR,
        prefix=".text_classifier-",
        suffix=".joblib.tmp",
    )

    os.close(descriptor)
    
    temporary_path = Path(temporary_name)
    rollback_path: Path | None = None

    try:
        joblib.dump(classifier, temporary_path)
        os.chmod(temporary_path, 0o640)

        with temporary_path.open("rb") as model_file:
            os.fsync(model_file.fileno())

        digest = _file_sha256(temporary_path)

        if ADAM_TEXT_CLASSIFIER_MODEL_PATH.exists():
            rollback_path = ADAM_MODELS_DIR / f".text_classifier-{uuid4()}.rollback"
            os.link(ADAM_TEXT_CLASSIFIER_MODEL_PATH, rollback_path)

        os.replace(temporary_path, ADAM_TEXT_CLASSIFIER_MODEL_PATH)

        return digest, rollback_path
    except Exception:
        temporary_path.unlink(missing_ok=True)

        if rollback_path is not None:
            rollback_path.unlink(missing_ok=True)
        raise


def _restore_model(rollback_path: Path | None) -> None:
    """Restore the previous model after a persistence failure."""
    if rollback_path is None:
        ADAM_TEXT_CLASSIFIER_MODEL_PATH.unlink(missing_ok=True)
        return

    os.replace(rollback_path, ADAM_TEXT_CLASSIFIER_MODEL_PATH)


def _persist_success(
    training_run_id: int,
    metadata: dict[str, Any],
) -> None:
    """Persist training metrics and activate the new model."""
    relative_model_path = str(ADAM_TEXT_CLASSIFIER_MODEL_PATH.relative_to(ROOT_DIR))

    with db.transaction(ADAM_DB_PATH) as connection:
        db.execute_on(
            connection,
            "UPDATE adam_training_runs SET is_active = 0 WHERE is_active = 1",
        )

        cursor = db.execute_on(
            connection,
            """
            UPDATE adam_training_runs
            SET status = 'success', completed_at = CURRENT_TIMESTAMP,
                model_id = ?, model_joblib_filepath = ?,
                evaluation_chart_filepath = ?, model_sha256 = ?,
                training_records = ?, testing_records = ?, labels = ?,
                labels_count = ?, training_accuracy = ?, testing_accuracy = ?,
                precision_macro = ?, recall_macro = ?, f1_macro = ?,
                parameters_json = ?, random_state = ?,
                scikit_learn_version = ?, joblib_version = ?,
                error_message = NULL, is_active = 1
            WHERE id = ? AND status = 'running'
            """,
            (
                metadata["model_id"],
                relative_model_path,
                metadata["evaluation_chart_filepath"],
                metadata["model_sha256"],
                metadata["training_records"],
                metadata["testing_records"],
                json.dumps(metadata["labels"], ensure_ascii=False),
                len(metadata["labels"]),
                metadata["training_accuracy"],
                metadata["testing_accuracy"],
                metadata["precision_macro"],
                metadata["recall_macro"],
                metadata["f1_macro"],
                json.dumps(metadata["parameters"], sort_keys=True),
                ADAM_TEXT_CLASSIFIER_RANDOM_STATE,
                sklearn.__version__,
                joblib.__version__,
                training_run_id,
            ),
        )

        if cursor.rowcount != 1:
            raise ValueError("The ADAM training result could not be persisted.")
