from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web.constants import TEMPLATE_DIR


templates = Jinja2Templates(directory=TEMPLATE_DIR)


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for firewall NAT pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def render_nat_rules(request: Request) -> HTMLResponse:
    """Render the firewall NAT rules template."""
    return templates.TemplateResponse(
        request,
        "firewall/nat_rules.html",
        context=page_context(request, "NAT Rules"),
    )
