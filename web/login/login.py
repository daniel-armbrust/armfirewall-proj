from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from web import auth
from web.constants import TEMPLATE_DIR
from web.context import menu_context


templates = Jinja2Templates(directory=TEMPLATE_DIR)


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for login pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "anonymous",
        "current_path": request.url.path,
        "menu": menu_context(),
    }


def redirect_after_login(request: Request, user: dict[str, Any], next_url: str | None = None) -> RedirectResponse:
    """Return the correct post-login redirect for the current user."""
    if int(user.get("must_change_password") or 0) == 1:
        return RedirectResponse(auth.CHANGE_PASSWORD_PATH, status_code=303)

    next_url = next_url or request.query_params.get("next") or "/"
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"
    return RedirectResponse(next_url, status_code=303)


async def read_form(request: Request) -> dict[str, str]:
    """Read URL-encoded form data without requiring extra multipart dependencies."""
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def render_login(request: Request, error: str | None = None) -> HTMLResponse:
    """Render the login page."""
    current_user = auth.get_current_user(request)
    if current_user and int(current_user.get("must_change_password") or 0) == 0:
        return RedirectResponse("/", status_code=303)

    context = page_context(request, "Login")
    context["error"] = error
    context["next_url"] = request.query_params.get("next", "/")
    return templates.TemplateResponse(
        request,
        "login/login.html",
        context=context,
    )


async def process_login(request: Request) -> Response:
    """Authenticate submitted credentials and create a web session."""
    form = await read_form(request)
    username = form.get("username", "").strip()
    password = form.get("password", "")

    user, error = auth.authenticate(username, password, request)
    if error or not user:
        return render_login(request, error or "Invalid username or password.")

    response = redirect_after_login(request, user, form.get("next"))
    auth.create_session(user, request, response)
    return response


def render_change_password(request: Request, error: str | None = None) -> HTMLResponse:
    """Render the mandatory password change page."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(auth.LOGIN_PATH, status_code=303)

    context = page_context(request, "Change Password")
    context["user_name"] = user["username"]
    context["error"] = error
    return templates.TemplateResponse(
        request,
        "login/change_password.html",
        context=context,
    )


async def process_change_password(request: Request) -> Response:
    """Validate and persist a mandatory password change."""
    user = auth.get_current_user(request)
    if not user:
        return RedirectResponse(auth.LOGIN_PATH, status_code=303)

    form = await read_form(request)
    current_password = form.get("current_password", "")
    new_password = form.get("new_password", "")
    confirm_password = form.get("confirm_password", "")

    if not auth.verify_password(current_password, user["password_hash"]):
        return render_change_password(request, "Current password is invalid.")
    if len(new_password) < 8:
        return render_change_password(request, "New password must have at least 8 characters.")
    if new_password != confirm_password:
        return render_change_password(request, "Password confirmation does not match.")
    if current_password == new_password:
        return render_change_password(request, "New password must be different from the current password.")

    auth.change_password(user, new_password)
    auth.record_login_event(user["username"], "password_change", request, user_id=user["id"], message="Password changed.")
    return RedirectResponse("/", status_code=303)


def process_logout(request: Request) -> Response:
    """Revoke the current session and redirect to login."""
    user = auth.get_current_user(request)
    if user:
        auth.record_login_event(user["username"], "logout", request, user_id=user["id"], message="User logged out.")
    auth.revoke_session(request)
    response = RedirectResponse(auth.LOGIN_PATH, status_code=303)
    auth.clear_session_cookie(response)
    return response
