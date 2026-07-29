"""Request models for the ADAM Web API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.constants import ADAM_TRANSCRIPTION_MAX_CHARS


class AdamTranscriptionPayload(BaseModel):
    """Voice transcription received from the browser."""

    text: str = Field(min_length=1, max_length=ADAM_TRANSCRIPTION_MAX_CHARS)
    language: str = Field(min_length=2, max_length=16)


class AdamPlaygroundInferencePayload(BaseModel):
    """Text submitted to the ADAM Playground classifier."""

    text: str = Field(min_length=1, max_length=ADAM_TRANSCRIPTION_MAX_CHARS)
