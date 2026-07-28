from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from web.settings import system_logs as system_logs_views
from web.settings import users as user_views
from web.settings.oci_integration import api as api_oci_integration
from web.settings import views as settings_views


router = APIRouter()


@router.get("/armfirewall/settings", response_class=HTMLResponse)
def settings_runtime(request: Request) -> HTMLResponse:
    """Render the ArmFirewall Runtime Settings page."""
    return settings_views.render_runtime_settings(request)


@router.put("/api/settings/runtime/oci")
def api_save_oci_integration(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Save OCI integration configuration in the protected runtime config directory."""
    try:
        return api_oci_integration.save_oci_integration(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Could not save OCI integration configuration.") from exc


@router.get("/api/settings/runtime/oci")
def api_get_oci_integration() -> dict[str, Any]:
    """Return saved OCI integration metadata."""
    return api_oci_integration.get_oci_integration()


@router.get("/api/settings/runtime/oci/regions")
def api_list_oci_regions() -> dict[str, Any]:
    """Return OCI regions supported by the installed SDK."""
    return api_oci_integration.list_oci_regions()


@router.delete("/api/settings/runtime/oci")
def api_delete_oci_integration() -> dict[str, Any]:
    """Delete the saved OCI integration configuration."""
    try:
        return api_oci_integration.delete_oci_integration()
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Could not delete OCI integration configuration.") from exc


@router.post("/api/settings/runtime/oci/test")
def api_test_oci_integration() -> dict[str, Any]:
    """Validate saved OCI integration material."""
    try:
        return api_oci_integration.test_oci_integration()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Could not validate OCI integration configuration.") from exc


@router.get("/armfirewall/users", response_class=HTMLResponse)
def settings_users(request: Request) -> HTMLResponse:
    """Render the Settings / Users page."""
    return settings_views.render_users(request)


@router.get("/armfirewall/system-logs", response_class=HTMLResponse)
def settings_system_logs(request: Request) -> HTMLResponse:
    """Render the ArmFirewall / System Logs page."""
    return settings_views.render_system_logs(request)


@router.get("/api/settings/system-logs")
def api_system_logs(limit: int = 200) -> dict[str, Any]:
    """Return recent ArmFirewall system logs."""
    return system_logs_views.list_logs(limit)


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
