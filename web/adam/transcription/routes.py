"""Route declarations for ADAM transcription."""

from fastapi import APIRouter

from .api import api_receive_transcription
from .models import AdamTranscriptionPayload


router = APIRouter()


@router.post("/api/adam/transcription")
def receive_transcription(
    payload: AdamTranscriptionPayload,
) -> dict[str, str]:
    """Receive a browser voice transcription."""
    return api_receive_transcription(payload)
