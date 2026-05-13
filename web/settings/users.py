from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web import auth
from core import db
from core.constants import USERS_DB_PATH
from web.constants import TEMPLATE_DIR
from web.context import menu_context


templates = Jinja2Templates(directory=TEMPLATE_DIR)
VALID_ROLES = {"admin", "operator", "viewer"}


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for Settings pages."""
    current_user = auth.get_current_user(request) or {}
    return {
        "request": request,
        "title": title,
        "user_name": current_user.get("username", "admin"),
        "current_path": request.url.path,
        "menu": menu_context(),
    }


def render_users(request: Request) -> HTMLResponse:
    """Render the Settings / Users page."""
    return templates.TemplateResponse(
        request,
        "settings/users.html",
        context=page_context(request, "Users"),
    )


def normalize_username(value: Any) -> str:
    """Return a clean username or raise a validation error."""
    username = str(value or "").strip()
    if len(username) < 3 or len(username) > 64:
        raise ValueError("Username must have between 3 and 64 characters.")
    if not all(char.isalnum() or char in "._-" for char in username):
        raise ValueError("Username may contain only letters, numbers, dot, dash and underscore.")
    return username


def normalize_role(value: Any) -> str:
    """Return a supported user role or raise a validation error."""
    role = str(value or "viewer").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError("Invalid user role.")
    return role


def normalize_bool(value: Any, *, default: bool = False) -> int:
    """Convert common JSON values to a SQLite boolean integer."""
    if value is None:
        return 1 if default else 0
    return 1 if bool(value) else 0


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    """Return a user row without password material."""
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row.get("display_name") or "",
        "role": row["role"],
        "enabled": int(row["enabled"]),
        "protected": int(row["protected"]),
        "must_change_password": int(row["must_change_password"]),
        "failed_login_count": int(row["failed_login_count"]),
        "locked_until": row.get("locked_until") or "",
        "last_login_at": row.get("last_login_at") or "",
        "last_login_ip": row.get("last_login_ip") or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_users() -> dict[str, Any]:
    """Return all configured GUI users."""
    users = db.fetch_all(
        """
        SELECT id, username, display_name, role, enabled, protected,
               must_change_password, failed_login_count, locked_until,
               last_login_at, last_login_ip, created_at, updated_at
          FROM users
         ORDER BY protected DESC, username
        """,
        db_path=USERS_DB_PATH,
    )
    return {"users": [public_user(user) for user in users]}


def get_user(user_id: int) -> dict[str, Any]:
    """Return one user by id or raise a validation error."""
    user = db.fetch_one(
        """
        SELECT *
          FROM users
         WHERE id = ?
        """,
        (user_id,),
        db_path=USERS_DB_PATH,
    )
    if not user:
        raise ValueError("User not found.")
    return user


def create_user(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new local GUI user."""
    username = normalize_username(payload.get("username"))
    display_name = str(payload.get("display_name") or "").strip() or None
    role = normalize_role(payload.get("role"))
    password = str(payload.get("password") or "")
    if len(password) < 4:
        raise ValueError("Password must have at least 4 characters.")

    must_change_password = normalize_bool(payload.get("must_change_password"), default=True)
    try:
        with db.transaction(USERS_DB_PATH) as conn:
            cursor = db.execute_on(
                conn,
                """
                INSERT INTO users (
                     username,
                     display_name,
                     password_hash,
                     password_changed_at,
                     must_change_password,
                     role,
                     enabled,
                     protected
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, 1, 0)
                """,
                (username, display_name, auth.hash_password(password), must_change_password, role),
            )
            user_id = cursor.lastrowid
    except db.DatabaseError as exc:
        raise ValueError("Could not create user. Username may already exist.") from exc

    return public_user(get_user(int(user_id)))


def update_user(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update editable profile and access fields for one user."""
    user = get_user(user_id)
    display_name = str(payload.get("display_name") or "").strip() or None
    role = normalize_role(payload.get("role", user["role"]))
    if int(user["protected"]) == 1 and role != user["role"]:
        raise ValueError("Protected user role cannot be changed.")
    must_change_password = normalize_bool(
        payload.get("must_change_password"),
        default=bool(user["must_change_password"]),
    )

    db.execute(
        """
        UPDATE users
           SET display_name = ?,
               role = ?,
               must_change_password = ?,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
        (display_name, role, must_change_password, user_id),
        db_path=USERS_DB_PATH,
    )
    return public_user(get_user(user_id))


def set_user_enabled(user_id: int, enabled: bool, request: Request) -> dict[str, Any]:
    """Enable or disable a non-protected user."""
    user = get_user(user_id)
    current_user = auth.get_current_user(request) or {}
    if int(user["protected"]) == 1 and not enabled:
        raise ValueError("Protected users cannot be disabled.")
    if current_user.get("id") == user_id and not enabled:
        raise ValueError("Current user cannot disable itself.")

    db.execute(
        """
        UPDATE users
           SET enabled = ?,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
        (1 if enabled else 0, user_id),
        db_path=USERS_DB_PATH,
    )
    return public_user(get_user(user_id))


def reset_password(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Reset a user password and optionally require change on next login."""
    get_user(user_id)
    password = str(payload.get("password") or "")
    if len(password) < 4:
        raise ValueError("Password must have at least 4 characters.")
    must_change_password = normalize_bool(payload.get("must_change_password"), default=True)

    db.execute(
        """
        UPDATE users
           SET password_hash = ?,
               password_changed_at = CURRENT_TIMESTAMP,
               must_change_password = ?,
               failed_login_count = 0,
               locked_until = NULL,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
        (auth.hash_password(password), must_change_password, user_id),
        db_path=USERS_DB_PATH,
    )
    return public_user(get_user(user_id))


def delete_user(user_id: int, request: Request) -> None:
    """Delete a non-protected user."""
    user = get_user(user_id)
    current_user = auth.get_current_user(request) or {}
    if int(user["protected"]) == 1:
        raise ValueError("Protected users cannot be deleted.")
    if current_user.get("id") == user_id:
        raise ValueError("Current user cannot delete itself.")

    with db.transaction(USERS_DB_PATH) as conn:
        db.execute_on(
            conn,
            """
            DELETE FROM user_sessions
             WHERE user_id NOT IN (SELECT id FROM users)
            """,
        )
        db.execute_on(
            conn,
            """
            DELETE FROM user_login_events
             WHERE user_id IS NOT NULL
               AND user_id NOT IN (SELECT id FROM users)
            """,
        )
        db.execute_on(conn, "DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
        db.execute_on(conn, "DELETE FROM user_login_events WHERE user_id = ?", (user_id,))
        db.execute_on(conn, "DELETE FROM users WHERE id = ?", (user_id,))
