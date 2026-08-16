"""Request and response models for ADAM Playground."""

from dataclasses import asdict, dataclass

from pydantic import BaseModel, Field

from core.constants import ADAM_TRANSCRIPTION_MAX_CHARS
from web.adam.text_classification.inference import IntentPrediction


class AdamPlaygroundInferencePayload(BaseModel):
    """Text submitted to the ADAM Playground classifier."""

    text: str = Field(min_length=1, max_length=ADAM_TRANSCRIPTION_MAX_CHARS)


@dataclass(frozen=True)
class PlaygroundInferenceResult:
    """One result returned by the ADAM Playground inference service."""

    mode: str
    prediction: IntentPrediction

    def to_dict(self) -> dict[str, object]:
        """Return an API-safe representation of the inference result."""
        return {
            "mode": self.mode,
            "prediction": asdict(self.prediction),
        }
