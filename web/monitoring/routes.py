from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from web.monitoring import views as monitoring_views


router = APIRouter()


@router.get("/api/monitoring/cpu-mem")
def api_monitoring_cpu_mem() -> dict[str, Any]:
    """Return CPU and memory monitoring graph metadata."""
    return monitoring_views.get_cpu_mem_graphs()


@router.get("/api/monitoring/network")
def api_monitoring_network() -> dict[str, Any]:
    """Return network interface monitoring graph metadata."""
    return monitoring_views.get_network_graphs()


@router.get("/api/monitoring/system")
def api_monitoring_system() -> dict[str, Any]:
    """Return system monitoring graph metadata."""
    return monitoring_views.get_system_graphs()


@router.get("/api/monitoring/socket-states")
def api_monitoring_socket_states() -> dict[str, Any]:
    """Return socket state monitoring graph metadata."""
    return monitoring_views.get_socket_state_graphs()


@router.get("/api/monitoring/filesystem")
def api_monitoring_filesystem() -> dict[str, Any]:
    """Return filesystem monitoring graph metadata."""
    return monitoring_views.get_filesystem_graphs()


@router.get("/api/monitoring/latency")
def api_monitoring_latency() -> dict[str, Any]:
    """Return latency monitoring graph metadata."""
    return monitoring_views.get_latency_graphs()


@router.post("/api/monitoring/latency")
def api_create_monitoring_latency_target(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create one latency monitoring target."""
    try:
        return {"target": monitoring_views.create_latency_target(payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/monitoring/latency/{target_id}")
def api_update_monitoring_latency_target(target_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Update one latency monitoring target."""
    try:
        return {"target": monitoring_views.update_latency_target(target_id, payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/monitoring/latency/{target_id}/enabled")
def api_set_monitoring_latency_target_enabled(target_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Enable or disable one latency monitoring target."""
    try:
        enabled = bool(payload.get("enabled"))
        return {"target": monitoring_views.set_latency_target_enabled(target_id, enabled)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/monitoring/latency/{target_id}")
def api_delete_monitoring_latency_target(target_id: int) -> dict[str, str]:
    """Delete one latency monitoring target."""
    try:
        monitoring_views.delete_latency_target(target_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "deleted"}


@router.get("/api/monitoring/disk")
def api_monitoring_disk() -> dict[str, Any]:
    """Return filesystem monitoring graph metadata for the legacy disk API."""
    return monitoring_views.get_filesystem_graphs()


@router.get("/monitoring/cpu-mem", response_class=HTMLResponse)
def monitoring_cpu_mem(request: Request) -> HTMLResponse:
    """Render the CPU and memory monitoring page."""
    return monitoring_views.render_cpu_mem(request)


@router.get("/monitoring/network", response_class=HTMLResponse)
def monitoring_network(request: Request) -> HTMLResponse:
    """Render the network monitoring page."""
    return monitoring_views.render_network(request)


@router.get("/monitoring/system", response_class=HTMLResponse)
def monitoring_system(request: Request) -> HTMLResponse:
    """Render the system monitoring page."""
    return monitoring_views.render_system(request)


@router.get("/monitoring/socket-states", response_class=HTMLResponse)
def monitoring_socket_states(request: Request) -> HTMLResponse:
    """Render the socket states monitoring page."""
    return monitoring_views.render_socket_states(request)


@router.get("/monitoring/filesystem", response_class=HTMLResponse)
def monitoring_filesystem(request: Request) -> HTMLResponse:
    """Render the filesystem monitoring page."""
    return monitoring_views.render_filesystem(request)


@router.get("/monitoring/latency", response_class=HTMLResponse)
def monitoring_latency(request: Request) -> HTMLResponse:
    """Render the latency monitoring page."""
    return monitoring_views.render_latency(request)


@router.get("/monitoring/disk", response_class=HTMLResponse)
def monitoring_disk(request: Request) -> HTMLResponse:
    """Render the legacy disk monitoring page as filesystem monitoring."""
    return monitoring_views.render_filesystem(request)
