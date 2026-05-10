from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


ROOT_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=[ROOT_DIR / "web" / "templates", ROOT_DIR / "templates"])


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for login pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "anonymous",
        "current_path": request.url.path,
    }


def render_login(request: Request) -> HTMLResponse:
    """Render the login page."""
    return templates.TemplateResponse(
        request,
        "login/login.html",
        context=page_context(request, "Login"),
    )
