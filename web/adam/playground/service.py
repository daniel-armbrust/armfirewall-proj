"""Inference service used by the ADAM Playground."""

from __future__ import annotations

from core.constants import ADAM_TRANSCRIPTION_MAX_CHARS
from .models import PlaygroundInferenceResult
from web.adam.text_classification.inference import AdamInferenceError, infer_intent


TEXT_CLASSIFICATION_MODE = "text-classification"


class PlaygroundInferenceError(RuntimeError):
    """Raised when a Playground inference request cannot be completed."""


def infer_text_classification(text: str) -> PlaygroundInferenceResult:
    """Run the active shared text-classification model for Playground input."""
    normalized_text = str(text or "").strip()
    
    if not normalized_text:
        raise PlaygroundInferenceError("Input text is required.")
    if len(normalized_text) > ADAM_TRANSCRIPTION_MAX_CHARS:
        raise PlaygroundInferenceError(
            f"Input text cannot exceed {ADAM_TRANSCRIPTION_MAX_CHARS} characters."
        )

    try:
        prediction = infer_intent(normalized_text)
    except (AdamInferenceError, ValueError) as exc:
        raise PlaygroundInferenceError(str(exc)) from exc

    return PlaygroundInferenceResult(
        mode=TEXT_CLASSIFICATION_MODE,
        prediction=prediction,
    )


__all__ = [
    "PlaygroundInferenceError",
    "TEXT_CLASSIFICATION_MODE",
    "infer_text_classification",
]
