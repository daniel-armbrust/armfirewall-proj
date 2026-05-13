from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web.constants import TEMPLATE_DIR
from web.context import menu_context


templates = Jinja2Templates(directory=TEMPLATE_DIR)


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for Work Requests pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
        "menu": menu_context(),
    }


def render_work_requests(request: Request) -> HTMLResponse:
    """Render the generic Work Requests page."""
    return templates.TemplateResponse(
        request,
        "common/page.html",
        context=page_context(request, "Work Requests") | {"section": "workrequests"},
    )
