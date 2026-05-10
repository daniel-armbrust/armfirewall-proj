from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


ROOT_DIR = Path(__file__).resolve().parents[3]
templates = Jinja2Templates(directory=[ROOT_DIR / "web" / "templates", ROOT_DIR / "templates"])


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for service pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def render_proxy(request: Request) -> HTMLResponse:
    """Render the Proxy service template."""
    return templates.TemplateResponse(
        request,
        "services/proxy.html",
        context=page_context(request, "Proxy"),
    )
