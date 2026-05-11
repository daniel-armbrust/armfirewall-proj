from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from web.login import login as login_views


router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login(request: Request) -> HTMLResponse:
    """Render the login page."""
    return login_views.render_login(request)


@router.post("/login", response_class=Response)
async def login_post(request: Request) -> Response:
    """Process a submitted login form."""
    return await login_views.process_login(request)


@router.get("/login/change-password", response_class=HTMLResponse)
def change_password(request: Request) -> HTMLResponse:
    """Render the mandatory password change page."""
    return login_views.render_change_password(request)


@router.post("/login/change-password", response_class=Response)
async def change_password_post(request: Request) -> Response:
    """Process a submitted password change form."""
    return await login_views.process_change_password(request)


@router.get("/logout", response_class=Response)
def logout(request: Request) -> Response:
    """Logout the current user."""
    return login_views.process_logout(request)
