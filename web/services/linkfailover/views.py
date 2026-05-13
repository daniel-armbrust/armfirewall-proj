from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web.constants import TEMPLATE_DIR


templates = Jinja2Templates(directory=TEMPLATE_DIR)


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for the Link Failover page."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def render_linkfailover(request: Request) -> HTMLResponse:
    """Render the Link Failover service template."""
    return templates.TemplateResponse(
        request,
        "services/linkfailover.html",
        context=page_context(request, "Link Failover"),
    )
