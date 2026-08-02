"""Route declarations for the ADAM user interface and APIs."""

from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import HTMLResponse

from web.adam import views
from web.adam.websocket import adam_websocket

router = APIRouter()

@router.get("/armfirewall/adam", response_class=HTMLResponse)
def adam_page(request: Request) -> HTMLResponse:
    """Render the ADAM page."""
    return views.render_adam(request)


@router.websocket("/ws/adam")
async def adam_command_websocket(websocket: WebSocket) -> None:
    """Keep the authenticated ADAM command WebSocket open."""
    await adam_websocket(websocket)
