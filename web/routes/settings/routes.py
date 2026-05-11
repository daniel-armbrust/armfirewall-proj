from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from web.settings import users as user_views


router = APIRouter()


@router.get("/settings/users", response_class=HTMLResponse)
def settings_users(request: Request) -> HTMLResponse:
    """Render the Settings / Users page."""
    return user_views.render_users(request)


@router.get("/api/settings/users")
def api_list_users() -> dict[str, Any]:
    """Return all configured GUI users."""
    return user_views.list_users()


@router.post("/api/settings/users")
def api_create_user(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create one GUI user."""
    try:
        return {"user": user_views.create_user(payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/settings/users/{user_id}")
def api_update_user(user_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Update one GUI user."""
    try:
        return {"user": user_views.update_user(user_id, payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/settings/users/{user_id}/enabled")
def api_set_user_enabled(user_id: int, request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Enable or disable one GUI user."""
    try:
        return {"user": user_views.set_user_enabled(user_id, bool(payload.get("enabled")), request)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/settings/users/{user_id}/password")
def api_reset_user_password(user_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Reset one GUI user password."""
    try:
        return {"user": user_views.reset_password(user_id, payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/settings/users/{user_id}")
def api_delete_user(user_id: int, request: Request) -> dict[str, str]:
    """Delete one GUI user."""
    try:
        user_views.delete_user(user_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "deleted"}
