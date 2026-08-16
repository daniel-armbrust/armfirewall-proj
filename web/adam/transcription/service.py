"""Local Whisper transcription for ADAM voice commands."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile

from faster_whisper import WhisperModel

from core.constants import (
    ADAM_WHISPER_COMPUTE_TYPE,
    ADAM_WHISPER_DEVICE,
    ADAM_WHISPER_LANGUAGE,
    ADAM_WHISPER_INITIAL_PROMPT,
    ADAM_WHISPER_MODEL_NAME,
)


class AdamTranscriptionError(RuntimeError):
    """Raised when ADAM cannot transcribe a recorded command."""


@lru_cache(maxsize=1)
def _model() -> WhisperModel:
    """Load the configured local Whisper model once per API process."""
    return WhisperModel(
        ADAM_WHISPER_MODEL_NAME,
        device=ADAM_WHISPER_DEVICE,
        compute_type=ADAM_WHISPER_COMPUTE_TYPE,
    )


def _whisper_language(language: str) -> str:
    """Map a browser language tag to Whisper's language code."""
    return ADAM_WHISPER_LANGUAGE if language.lower().startswith("en") else language[:2].lower()


def transcribe_command(audio: bytes, language: str) -> str:
    """Transcribe a WAV command using the local Whisper model."""
    if not audio:
        raise AdamTranscriptionError("Audio command is required.")

    temporary_file = NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        temporary_file.write(audio)
        temporary_file.close()
        segments, _ = _model().transcribe(
            temporary_file.name,
            language=_whisper_language(language),
            vad_filter=True,
            initial_prompt=ADAM_WHISPER_INITIAL_PROMPT,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
    except Exception as error:
        raise AdamTranscriptionError("Unable to transcribe the ADAM command.") from error
    finally:
        Path(temporary_file.name).unlink(missing_ok=True)

    if not text:
        raise AdamTranscriptionError("No speech was detected in the ADAM command.")
    return text
