"""ADAM WebSocket command-dialog processing."""

from __future__ import annotations

import json
import uuid
from random import choice as random_choice
from collections import deque

from fastapi import WebSocket

from core import log as logger
from core.constants import (
    ADAM_TEXT_CLASSIFIER_IGNORE_CONFIDENCE,
    ADAM_TEXT_CLASSIFIER_MIN_CONFIDENCE,
    ADAM_WEBSOCKET_LOG_SOURCE,
    ADAM_WEBSOCKET_REPEAT_PROMPTS,
)
from web.adam.command_extraction.service import (
    CommandExtractionError,
    extract_command,
)
from web.adam.text_classification.inference import AdamInferenceError, infer_intent
from web.adam.transcription.models import AdamTranscriptionPayload


async def send_event(websocket: WebSocket, event_type: str, **payload: object) -> None:
    """Send one typed ADAM WebSocket event."""
    await websocket.send_json({"type": event_type, **payload})


async def receive_command(websocket: WebSocket, processed_request_ids: deque[str]) -> None:
    """Validate, classify, and extract fields from one voice command."""
    try:
        message = json.loads(await websocket.receive_text())
    except json.JSONDecodeError:
        await send_event(websocket, "command.error", message="Invalid JSON message.")
        return

    if not isinstance(message, dict):
        await send_event(websocket, "command.error", message="Message must be a JSON object.")
        return

    event_type = str(message.get("type") or "")

    if event_type == "session.ping":
        await send_event(websocket, "session.pong")
        return

    if event_type != "command.submit":
        await send_event(websocket, "command.error", message="Unsupported message type.")
        return

    request_id = str(message.get("request_id") or "")

    try:
        uuid.UUID(request_id)
    except ValueError:
        await send_event(websocket, "command.error", message="A valid request_id is required.")
        return

    if request_id in processed_request_ids:
        await send_event(websocket, "command.accepted", request_id=request_id, duplicate=True)
        return

    try:
        command = AdamTranscriptionPayload.model_validate(
            {"text": message.get("text"), "language": message.get("language")}
        )
    except ValueError:
        await send_event(
            websocket,
            "command.error",
            request_id=request_id,
            message="Invalid command payload.",
        )
        return

    processed_request_ids.append(request_id)
    await send_event(websocket, "command.accepted", request_id=request_id)

    try:
        prediction = infer_intent(command.text)
    except AdamInferenceError:
        await send_event(
            websocket,
            "command.error",
            request_id=request_id,
            message="ADAM could not classify the voice command.",
        )
        return

    await send_event(
        websocket,
        "intent.detected",
        request_id=request_id,
        **prediction.to_dict(),
    )

    if prediction.confidence < ADAM_TEXT_CLASSIFIER_IGNORE_CONFIDENCE:
        await send_event(
            websocket,
            "command.response",
            request_id=request_id,
            status="ignored",
            confidence=prediction.confidence,
            minimum_confidence=ADAM_TEXT_CLASSIFIER_IGNORE_CONFIDENCE,
        )
        return

    if prediction.confidence < ADAM_TEXT_CLASSIFIER_MIN_CONFIDENCE:
        await send_event(
            websocket,
            "command.response",
            request_id=request_id,
            status="repeat",
            message=random_choice(ADAM_WEBSOCKET_REPEAT_PROMPTS),
            language=command.language,
            confidence=prediction.confidence,
            minimum_confidence=ADAM_TEXT_CLASSIFIER_MIN_CONFIDENCE,
        )
        return

    try:
        extracted_command = extract_command(command.text, prediction.intent)
    except CommandExtractionError as exc:
        await send_event(
            websocket,
            "command.response",
            request_id=request_id,
            status="unsupported",
            message=str(exc),
            language=command.language,
            intent=prediction.intent,
        )
        return

    extracted_payload = extracted_command.to_dict()
    logger.log(
        f"Extracted ADAM command JSON: {json.dumps(extracted_payload, sort_keys=True)}",
        source=ADAM_WEBSOCKET_LOG_SOURCE,
    )

    # The command executor will consume this JSON when firewall API dispatch is added.
    await send_event(
        websocket,
        "command.response",
        request_id=request_id,
        status="extracted",
        message="Voice command intent and fields extracted.",
        language=command.language,
        command=extracted_payload,
    )
