"""Request models for ADAM wake-word profiles."""

from pydantic import BaseModel, Field


class AdamWakeWordProfilePayload(BaseModel):
    """Browser-generated acoustic templates for one ADAM wake-word profile."""

    profile_key: str = Field(min_length=1, max_length=64)
    templates: list[list[list[float]]]
    threshold: float
