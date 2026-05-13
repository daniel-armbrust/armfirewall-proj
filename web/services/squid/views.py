from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web.constants import TEMPLATE_DIR
from web.services.squid import api as squid_api


templates = Jinja2Templates(directory=TEMPLATE_DIR)


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for Squid pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def render_squid(request: Request) -> HTMLResponse:
    """Render the Squid service template."""
    if not squid_api.squid_service_installed():
        raise HTTPException(status_code=404, detail="Squid service is not installed.")

    return templates.TemplateResponse(
        request,
        "services/squid.html",
        context=page_context(request, "Squid"),
    )
