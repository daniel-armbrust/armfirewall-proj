"""Authenticated WebSocket gateway for ADAM voice commands."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import deque
from urllib.parse import urlparse

from fastapi import WebSocket, WebSocketDisconnect

from web import auth
from web.adam.inference import AdamInferenceError, infer_intent
from web.adam.models import AdamTranscriptionPayload
from web.constants import SESSION_COOKIE
from web.services.api import service_enabled


_CLOSE_UNAUTHORIZED = 4401
_CLOSE_FORBIDDEN = 4403
_POLL_INTERVAL_SECONDS = 2
_MAX_PROCESSED_REQUESTS = 128


def adam_is_enabled() -> bool:
    """Return whether ADAM is currently available to authenticated users."""
    return service_enabled("armfirewall-adam")


def origin_is_allowed(websocket: WebSocket) -> bool:
    """Accept same-origin browser WebSocket requests and non-browser clients without Origin."""
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host")

    if not origin or not host:
        return True

    return urlparse(origin).netloc == host


async def send_event(websocket: WebSocket, event_type: str, **payload: object) -> None:
    """Send one typed ADAM WebSocket event."""
    await websocket.send_json({"type": event_type, **payload})


async def receive_command(websocket: WebSocket, processed_request_ids: deque[str]) -> None:
    """Validate and acknowledge one browser voice command submission."""
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
        await send_event(websocket, "command.error", request_id=request_id, message="Invalid command payload.")
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

    # The command orchestrator will replace this acknowledgement when firewall
    # query dispatch and streamed ADAM responses are connected.
    await send_event(
        websocket,
        "command.response",
        request_id=request_id,
        status="classified",
        message="Voice command classified.",
        language=command.language,
    )


async def adam_websocket(websocket: WebSocket) -> None:
    """Keep an authenticated ADAM command channel open while ADAM is enabled."""
    if not origin_is_allowed(websocket):
        await websocket.close(code=_CLOSE_FORBIDDEN, reason="Origin is not allowed.")
        return

    user = auth.get_user_from_session_token(websocket.cookies.get(SESSION_COOKIE))

    if user is None:
        await websocket.close(code=_CLOSE_UNAUTHORIZED, reason="Authentication required.")
        return

    if int(user.get("must_change_password") or 0) == 1:
        await websocket.close(code=_CLOSE_FORBIDDEN, reason="Password change required.")
        return

    if not adam_is_enabled():
        await websocket.close(code=_CLOSE_FORBIDDEN, reason="ADAM is disabled.")
        return

    await websocket.accept()
    await send_event(websocket, "session.ready", user=str(user["username"]))
    processed_request_ids: deque[str] = deque(maxlen=_MAX_PROCESSED_REQUESTS)

    try:
        while True:
            if not adam_is_enabled():
                await websocket.close(code=_CLOSE_FORBIDDEN, reason="ADAM is disabled.")
                return

            try:
                await asyncio.wait_for(
                    receive_command(websocket, processed_request_ids),
                    timeout=_POLL_INTERVAL_SECONDS,
                )
            except TimeoutError:
                continue
    except WebSocketDisconnect:
        return
