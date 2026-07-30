"""HTTP routes for receiving ADAM transcriptions."""

from __future__ import annotations

from web.adam import models


def api_receive_transcription(
    payload: models.AdamTranscriptionPayload,
) -> dict[str, str]:
    """Receive an ADAM voice transcription without processing it."""
    print(payload)
    return {"status": "received"}


__all__ = ["api_receive_transcription"]
