from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web.constants import TEMPLATE_DIR
from web.context import menu_context
from web.services.libreswan import api as libreswan_api


templates = Jinja2Templates(directory=TEMPLATE_DIR)


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for Libreswan pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
        "menu": menu_context(),
    }


def render_libreswan(request: Request) -> HTMLResponse:
    """Render the Libreswan service template."""
    if not libreswan_api.libreswan_service_installed():
        raise HTTPException(status_code=404, detail="Libreswan service is not installed.")

    return templates.TemplateResponse(
        request,
        "services/libreswan.html",
        context=page_context(request, "Libreswan"),
    )
