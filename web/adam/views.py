"""Template rendering helpers for ADAM pages."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.constants import ADAM_DATASET_MAX_BYTES
from web import auth
from web.constants import TEMPLATE_DIR
from web.context import menu_context


templates = Jinja2Templates(directory=TEMPLATE_DIR)


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create the shared template context for ADAM pages."""
    current_user = auth.get_current_user(request) or {}
    return {
        "request": request,
        "title": title,
        "user_name": current_user.get("username", "admin"),
        "current_path": request.url.path,
        "menu": menu_context(),
        "adam_dataset_max_mb": ADAM_DATASET_MAX_BYTES // (1024 * 1024),
    }


def render_adam(request: Request) -> HTMLResponse:
    """Render the main ADAM assistant page."""
    return templates.TemplateResponse(
        request,
        "adam/index.html",
        context=page_context(request, "Adam (IA)"),
    )
