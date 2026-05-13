from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web.constants import TEMPLATE_DIR


templates = Jinja2Templates(directory=TEMPLATE_DIR)


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for firewall filter pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def render_filter_rules(request: Request) -> HTMLResponse:
    """Render the firewall filter rules template."""
    return templates.TemplateResponse(
        request,
        "firewall/filter_rules.html",
        context=page_context(request, "Filter Rules"),
    )
