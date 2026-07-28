from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web import auth
from web.constants import TEMPLATE_DIR
from web.context import menu_context


templates = Jinja2Templates(directory=TEMPLATE_DIR)


def page_context(request: Request, title: str, *, section: str | None = None) -> dict[str, Any]:
    """Create shared template context for Settings pages."""
    current_user = auth.get_current_user(request) or {}
    context = {
        "request": request,
        "title": title,
        "user_name": current_user.get("username", "admin"),
        "current_path": request.url.path,
        "menu": menu_context(),
    }
    if section is not None:
        context["section"] = section
    return context


def render_runtime_settings(request: Request) -> HTMLResponse:
    """Render the Runtime Settings page."""
    return templates.TemplateResponse(
        request,
        "settings/runtime.html",
        context=page_context(request, "Runtime Settings", section="ArmFirewall"),
    )


def render_users(request: Request) -> HTMLResponse:
    """Render the Settings / Users page."""
    return templates.TemplateResponse(
        request,
        "settings/users.html",
        context=page_context(request, "Users"),
    )


def render_system_logs(request: Request) -> HTMLResponse:
    """Render the ArmFirewall system logs page."""
    return templates.TemplateResponse(
        request,
        "settings/system_logs.html",
        context=page_context(request, "System Logs"),
    )
