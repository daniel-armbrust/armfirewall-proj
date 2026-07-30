from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.dashboard import api as dashboard_api
from web.dashboard import views as dashboard_views


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Return a simple health status for service checks."""
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    """Render the default dashboard page."""
    return dashboard_views.render_dashboard(request)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request) -> HTMLResponse:
    """Render the dashboard page from its explicit route."""
    return dashboard_views.render_dashboard(request)


@router.get("/api/config")
def api_config() -> dict[str, str]:
    """Return application configuration values exposed to the UI."""
    return dashboard_api.read_conf()


@router.get("/api/dashboard")
def api_dashboard() -> dict[str, Any]:
    """Return dashboard data used by the frontend."""
    return dashboard_api.get_dashboard()
