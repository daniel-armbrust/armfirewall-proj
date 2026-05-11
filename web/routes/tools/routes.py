from __future__ import annotations

import subprocess
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from web.dashboard import views as dashboard_views
from web.tools import mtr as mtr_views
from web.tools import ping as ping_views
from web.tools import traceroute as traceroute_views


router = APIRouter()


@router.get("/tools/ping", response_class=HTMLResponse)
def tools_ping(request: Request) -> HTMLResponse:
    """Render the Tools / Ping page."""
    return ping_views.render_ping(request)


@router.get("/tools/mtr", response_class=HTMLResponse)
def tools_mtr(request: Request) -> HTMLResponse:
    """Render the Tools / MTR page."""
    return mtr_views.render_mtr(request)


@router.get("/tools/traceroute", response_class=HTMLResponse)
def tools_traceroute(request: Request) -> HTMLResponse:
    """Render the Tools / Traceroute page."""
    return traceroute_views.render_traceroute(request)


@router.get("/tools/packet-capture", response_class=HTMLResponse)
def tools_packet_capture(request: Request) -> HTMLResponse:
    """Render the Tools / Packet Capture page."""
    return dashboard_views.render_menu_page(request, "Packet Capture", "tools")


@router.get("/api/tools/ping")
def api_ping_context() -> dict[str, Any]:
    """Return ping form context."""
    return {"interfaces": ping_views.list_interfaces()}


@router.get("/api/tools/mtr")
def api_mtr_context() -> dict[str, Any]:
    """Return MTR form context."""
    return {"interfaces": mtr_views.list_interfaces()}


@router.get("/api/tools/traceroute")
def api_traceroute_context() -> dict[str, Any]:
    """Return traceroute form context."""
    return {"interfaces": traceroute_views.list_interfaces()}


@router.post("/api/tools/ping")
def api_run_ping(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Run one bounded ping command."""
    try:
        return ping_views.run_ping(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except subprocess.TimeoutExpired as exc:  # type: ignore[name-defined]
        raise HTTPException(status_code=408, detail="Ping command timed out.") from exc


@router.post("/api/tools/ping/stream")
def api_stream_ping(payload: dict[str, Any] = Body(...)) -> StreamingResponse:
    """Stream one bounded ping command in real time."""
    try:
        events = ping_views.stream_ping(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/tools/mtr/stream")
def api_stream_mtr(payload: dict[str, Any] = Body(...)) -> StreamingResponse:
    """Stream one bounded MTR command in report mode."""
    try:
        events = mtr_views.stream_mtr(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/tools/traceroute/stream")
def api_stream_traceroute(payload: dict[str, Any] = Body(...)) -> StreamingResponse:
    """Stream one bounded traceroute command in real time."""
    try:
        events = traceroute_views.stream_traceroute(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
