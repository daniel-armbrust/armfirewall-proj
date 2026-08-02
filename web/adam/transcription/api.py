"""HTTP routes for receiving ADAM transcriptions."""

from __future__ import annotations

from .models import AdamTranscriptionPayload


def api_receive_transcription(
    payload: AdamTranscriptionPayload,
) -> dict[str, str]:
    """Receive an ADAM voice transcription without processing it."""
    print(payload)
    return {"status": "received"}


__all__ = ["api_receive_transcription"]
