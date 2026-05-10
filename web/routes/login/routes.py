from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.login import login as login_views


router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login(request: Request) -> HTMLResponse:
    """Render the login page."""
    return login_views.render_login(request)
