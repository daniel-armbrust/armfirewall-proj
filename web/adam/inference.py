"""Inference helpers for the active ADAM text-classification model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Any

import joblib

from core import log as logger
from core.constants import ADAM_TEXT_CLASSIFIER_MODEL_PATH


LOG_SOURCE = "adam-inference"


class AdamInferenceError(RuntimeError):
    """Base error raised when ADAM intent inference cannot be completed."""


class AdamModelUnavailableError(AdamInferenceError):
    """Raised when no active ADAM classifier model is available."""


@dataclass(frozen=True)
class IntentPrediction:
    """One local ADAM intent-classification result."""

    intent: str
    confidence: float

    def to_dict(self) -> dict[str, str | float]:
        """Return a WebSocket-safe representation of the prediction."""
        return asdict(self)


_model_lock = RLock()
_cached_model: Any | None = None
_cached_signature: tuple[int, int] | None = None


def _model_signature(path: Path) -> tuple[int, int]:
    """Return a signature that changes whenever the atomically published model changes."""
    try:
        metadata = path.stat()
    except FileNotFoundError as exc:
        raise AdamModelUnavailableError("No trained ADAM text-classification model is available.") from exc

    if not path.is_file():
        raise AdamModelUnavailableError("The ADAM text-classification model is unavailable.")

    return metadata.st_mtime_ns, metadata.st_size


def _load_active_model() -> Any:
    """Load the active classifier and reload it only after a model publication."""
    global _cached_model, _cached_signature

    signature = _model_signature(ADAM_TEXT_CLASSIFIER_MODEL_PATH)

    with _model_lock:
        if _cached_model is not None and _cached_signature == signature:
            return _cached_model

        try:
            classifier = joblib.load(ADAM_TEXT_CLASSIFIER_MODEL_PATH)
        except Exception as exc:  # noqa: BLE001 - joblib exposes several load errors.
            raise AdamModelUnavailableError("The ADAM text-classification model could not be loaded.") from exc

        if not hasattr(classifier, "predict_proba") or not hasattr(classifier, "classes_"):
            raise AdamModelUnavailableError("The ADAM text-classification model has an invalid format.")

        _cached_model = classifier
        _cached_signature = signature
        return classifier


def infer_intent(text: str) -> IntentPrediction:
    """Classify one transcribed command using the active local ADAM model."""
    normalized_text = str(text or "").strip()

    if not normalized_text:
        raise ValueError("Text is required for ADAM intent inference.")

    logger.log(f"Received ADAM transcription: {normalized_text!r}", source=LOG_SOURCE)
    classifier = _load_active_model()

    try:
        probabilities = classifier.predict_proba([normalized_text])[0]
        index = max(range(len(probabilities)), key=lambda item: float(probabilities[item]))
        intent = str(classifier.classes_[index])
        confidence = float(probabilities[index])
    except Exception as exc:  # noqa: BLE001 - protect the WebSocket boundary from model errors.
        raise AdamInferenceError("ADAM intent inference failed.") from exc

    prediction = IntentPrediction(intent=intent, confidence=confidence)
    logger.log(
        f"ADAM inference result: intent={prediction.intent!r} confidence={prediction.confidence:.4f}",
        source=LOG_SOURCE,
    )
    return prediction
