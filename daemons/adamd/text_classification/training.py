"""Train and atomically publish the ADAM classifier model."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from core.hashing import sha256_file


def build_classifier(*, max_iterations: int, random_state: int) -> Pipeline:
    """Build the deterministic text-classification pipeline."""
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
                    max_iter=max_iterations,
                    random_state=random_state,
                ),
            ),
        ]
    )


def publish_model(
    classifier: Pipeline,
    *,
    models_dir: Path,
    model_path: Path,
) -> tuple[str, Path | None]:
    """Atomically replace the active model and retain a rollback link."""
    models_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=models_dir,
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

        digest = sha256_file(temporary_path)

        if model_path.exists():
            rollback_path = models_dir / f".text_classifier-{uuid4()}.rollback"
            os.link(model_path, rollback_path)

        os.replace(temporary_path, model_path)
        return digest, rollback_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        if rollback_path is not None:
            rollback_path.unlink(missing_ok=True)
        raise


def restore_model(model_path: Path, rollback_path: Path | None) -> None:
    """Restore the previous model after a persistence failure."""
    if rollback_path is None:
        model_path.unlink(missing_ok=True)
        return

    os.replace(rollback_path, model_path)
