"""Authenticated ADAM WebSocket connection handling."""

from __future__ import annotations

import asyncio
from collections import deque
from urllib.parse import urlparse

from fastapi import WebSocket, WebSocketDisconnect

from core.constants import (
    ADAM_WEBSOCKET_CLOSE_FORBIDDEN,
    ADAM_WEBSOCKET_CLOSE_UNAUTHORIZED,
    ADAM_WEBSOCKET_MAX_PROCESSED_REQUESTS,
    ADAM_WEBSOCKET_POLL_INTERVAL_SECONDS,
)
from web import auth
from web.constants import SESSION_COOKIE
from web.services.api import service_enabled

from .commands import receive_command, send_event


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


async def adam_websocket(websocket: WebSocket) -> None:
    """Keep an authenticated ADAM command channel open while ADAM is enabled."""
    if not origin_is_allowed(websocket):
        await websocket.close(
            code=ADAM_WEBSOCKET_CLOSE_FORBIDDEN,
            reason="Origin is not allowed.",
        )
        return

    user = auth.get_user_from_session_token(websocket.cookies.get(SESSION_COOKIE))

    if user is None:
        await websocket.close(
            code=ADAM_WEBSOCKET_CLOSE_UNAUTHORIZED,
            reason="Authentication required.",
        )
        return

    if int(user.get("must_change_password") or 0) == 1:
        await websocket.close(
            code=ADAM_WEBSOCKET_CLOSE_FORBIDDEN,
            reason="Password change required.",
        )
        return

    if not adam_is_enabled():
        await websocket.close(
            code=ADAM_WEBSOCKET_CLOSE_FORBIDDEN,
            reason="ADAM is disabled.",
        )
        return

    await websocket.accept()
    await send_event(websocket, "session.ready", user=str(user["username"]))
    processed_request_ids: deque[str] = deque(
        maxlen=ADAM_WEBSOCKET_MAX_PROCESSED_REQUESTS,
    )

    try:
        while True:
            if not adam_is_enabled():
                await websocket.close(
                    code=ADAM_WEBSOCKET_CLOSE_FORBIDDEN,
                    reason="ADAM is disabled.",
                )
                return

            try:
                await asyncio.wait_for(
                    receive_command(websocket, processed_request_ids),
                    timeout=ADAM_WEBSOCKET_POLL_INTERVAL_SECONDS,
                )
            except TimeoutError:
                continue
    except WebSocketDisconnect:
        return
