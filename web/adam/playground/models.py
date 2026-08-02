"""Request models for ADAM Playground."""

from pydantic import BaseModel, Field

from core.constants import ADAM_TRANSCRIPTION_MAX_CHARS


class AdamPlaygroundInferencePayload(BaseModel):
    """Text submitted to the ADAM Playground classifier."""

    text: str = Field(min_length=1, max_length=ADAM_TRANSCRIPTION_MAX_CHARS)
