"""Inference service used by the ADAM Playground."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from core.constants import ADAM_TRANSCRIPTION_MAX_CHARS
from web.adam.inference import AdamInferenceError, IntentPrediction, infer_intent


TEXT_CLASSIFICATION_MODE = "text-classification"


class PlaygroundInferenceError(RuntimeError):
    """Raised when a Playground inference request cannot be completed."""


@dataclass(frozen=True)
class PlaygroundInferenceResult:
    """One result returned by the ADAM Playground inference service."""

    mode: str
    prediction: IntentPrediction

    def to_dict(self) -> dict[str, object]:
        """Return an API-safe representation of the inference result."""
        return {"mode": self.mode, "prediction": asdict(self.prediction)}


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
    "PlaygroundInferenceResult",
    "TEXT_CLASSIFICATION_MODE",
    "infer_text_classification",
]
