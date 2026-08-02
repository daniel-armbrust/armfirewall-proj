"""Request models for ADAM voice transcription."""

from pydantic import BaseModel, Field

from core.constants import ADAM_TRANSCRIPTION_MAX_CHARS


class AdamTranscriptionPayload(BaseModel):
    """Voice transcription received from the browser."""

    text: str = Field(min_length=1, max_length=ADAM_TRANSCRIPTION_MAX_CHARS)
    language: str = Field(min_length=2, max_length=16)
