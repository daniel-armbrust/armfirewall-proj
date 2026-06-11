"""Train and publish the ADAM text intent classifier."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from core.constants import ADAM_DATASET_DIR, ADAM_MODELS_DIR

from .constants import (
    ACTIVE_MODEL_FILE_NAME,
    DATASET_METADATA_FILE_NAME,
    SOURCE_FILE_NAME,
)
from .request import AdamWorkRequest


def _normalize_uuid(value: object, *, field_name: str) -> str:
    """Return a canonical UUID for an external identifier."""
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"The {field_name} must be a valid UUID.") from exc


def _dataset_id(request: AdamWorkRequest) -> str:
    """Read and validate the immutable dataset identifier from the payload."""
    return _normalize_uuid(request.payload.get("dataset_id"), field_name="dataset_id")


def _load_dataset(dataset_id: str) -> tuple[list[str], list[str], dict[str, Any]]:
    """Load one normalized dataset from the protected runtime data directory."""
    dataset_dir = ADAM_DATASET_DIR / dataset_id
    source_path = dataset_dir / SOURCE_FILE_NAME
    metadata_path = dataset_dir / DATASET_METADATA_FILE_NAME

    if not source_path.is_file():
        raise FileNotFoundError(f"Dataset {dataset_id} was not found.")
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Metadata for dataset {dataset_id} was not found.")

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Metadata for dataset {dataset_id} is invalid.") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"Metadata for dataset {dataset_id} is invalid.")
    if _normalize_uuid(metadata.get("dataset_id"), field_name="metadata dataset_id") != dataset_id:
        raise ValueError(f"Metadata for dataset {dataset_id} is inconsistent.")

    texts: list[str] = []
    labels: list[str] = []
    with source_path.open("r", encoding="utf-8-sig", newline="") as dataset_file:
        reader = csv.DictReader(dataset_file)
        if tuple(reader.fieldnames or ()) != ("text", "label"):
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
        raise ValueError("The dataset does not contain training records.")
    if len(set(labels)) < 2:
        raise ValueError("The dataset must contain at least two labels.")
    return texts, labels, metadata


def _build_classifier() -> Pipeline:
    """Build the reproducible ADAM text classification pipeline."""
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
                LogisticRegression(max_iter=1_000, random_state=42),
            ),
        ]
    )


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    """Atomically write a private JSON metadata file."""
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}-",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o640)
        content = (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _atomic_joblib(path: Path, classifier: Pipeline) -> None:
    """Atomically publish a trusted model artifact."""
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}-",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        joblib.dump(classifier, temporary_path)
        os.chmod(temporary_path, 0o640)
        with temporary_path.open("rb") as model_file:
            os.fsync(model_file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def run_training_request(request: AdamWorkRequest) -> dict[str, Any]:
    """Train one classifier and atomically publish its model artifact."""
    dataset_id = _dataset_id(request)
    texts, labels, dataset_metadata = _load_dataset(dataset_id)
    classifier = _build_classifier()
    classifier.fit(texts, labels)

    ADAM_MODELS_DIR.mkdir(parents=True, exist_ok=True, mode=0o750)
    model_id = str(uuid4())
    model_file_name = f"adam-intent-{model_id}.joblib"
    metadata_file_name = f"adam-intent-{model_id}.json"
    model_path = ADAM_MODELS_DIR / model_file_name
    metadata_path = ADAM_MODELS_DIR / metadata_file_name
    classes = [str(value) for value in classifier.classes_]
    metadata = {
        "model_id": model_id,
        "model_file": model_file_name,
        "metadata_file": metadata_file_name,
        "dataset_id": dataset_id,
        "dataset_file_name": dataset_metadata.get("file_name", SOURCE_FILE_NAME),
        "work_request_id": request.work_request_id,
        "request_uid": request.request_uid,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "records": len(texts),
        "labels": classes,
        "training_accuracy": float(classifier.score(texts, labels)),
        "estimator": "LogisticRegression",
        "vectorizer": "TfidfVectorizer",
    }

    _atomic_joblib(model_path, classifier)
    try:
        _atomic_json(metadata_path, metadata)
        _atomic_json(ADAM_MODELS_DIR / ACTIVE_MODEL_FILE_NAME, metadata)
    except Exception:
        try:
            model_path.unlink()
        except FileNotFoundError:
            pass
        try:
            metadata_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return metadata
