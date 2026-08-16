"""HTTP API for transcribing ADAM voice commands."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

from core.constants import ADAM_TRANSCRIPTION_MAX_BYTES

from .service import AdamTranscriptionError, transcribe_command


async def api_transcribe_command(
    audio: UploadFile,
    language: str,
) -> dict[str, str]:
    """Transcribe one browser-recorded ADAM command with Whisper."""
    content = await audio.read(ADAM_TRANSCRIPTION_MAX_BYTES + 1)
    if len(content) > ADAM_TRANSCRIPTION_MAX_BYTES:
        raise HTTPException(status_code=413, detail="ADAM command audio is too large.")
    try:
        text = transcribe_command(content, language)
    except AdamTranscriptionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"text": text}


__all__ = ["api_transcribe_command"]
