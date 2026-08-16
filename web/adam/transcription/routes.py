"""Route declarations for ADAM transcription."""

from fastapi import APIRouter, File, Form, UploadFile

from .api import api_transcribe_command


router = APIRouter()


@router.post("/api/adam/transcription")
async def transcribe_command(
    audio: UploadFile = File(...),
    language: str = Form(...),
) -> dict[str, str]:
    """Transcribe an ADAM command recorded in the browser."""
    return await api_transcribe_command(audio, language)
