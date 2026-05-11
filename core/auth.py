"""Authentication helpers for ArmFirewall web sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from core import db


ROOT_DIR = Path(__file__).resolve().parents[1]
USERS_DB_PATH = ROOT_DIR / "db" / "users.db"
SESSION_COOKIE = "armfw_session"
SESSION_TTL = timedelta(hours=8)
LOGIN_PATH = "/login"
CHANGE_PASSWORD_PATH = "/login/change-password"
LOGOUT_PATH = "/logout"
PUBLIC_PREFIXES = ("/static/",)
AUTH_FLOW_PATHS = {LOGIN_PATH, CHANGE_PASSWORD_PATH}


def utc_now() -> datetime:
    """Return the current UTC datetime without relying on local timezone."""
    return datetime.now(UTC)


def sqlite_timestamp(value: datetime | None = None) -> str:
    """Format a datetime for storage in SQLite text columns."""
    return (value or utc_now()).strftime("%Y-%m-%d %H:%M:%S")


def parse_sqlite_timestamp(value: str | None) -> datetime | None:
    """Parse a SQLite timestamp as UTC."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def hash_session_token(token: str) -> str:
    """Hash a browser session token before database lookup or storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plain password against the stored self-describing hash."""
    try:
        algorithm, iterations, salt, digest = stored_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    try:
        rounds = int(iterations)
        expected = base64.b64decode(digest.encode("ascii"), validate=True)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds)
    return hmac.compare_digest(actual, expected)


def hash_password(password: str) -> str:
    """Create a PBKDF2-SHA256 hash for a user password."""
    iterations = 260000
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${base64.b64encode(digest).decode('ascii')}"


def wants_json(request: Request) -> bool:
    """Return whether an unauthenticated request should receive JSON."""
    accept = request.headers.get("accept", "")
    return request.url.path.startswith("/api/") or "application/json" in accept


def is_public_path(path: str) -> bool:
    """Return whether a path is allowed without an authenticated session."""
    return path in AUTH_FLOW_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def login_redirect(request: Request) -> RedirectResponse:
    """Redirect a browser request to the login page preserving the next URL."""
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    return RedirectResponse(f"{LOGIN_PATH}?next={quote(next_path)}", status_code=303)


def unauthorized_response(request: Request) -> Response:
    """Return a redirect or JSON response for unauthenticated requests."""
    if wants_json(request):
        return JSONResponse({"detail": "Authentication required."}, status_code=401)
    return login_redirect(request)


def session_cookie_params(request: Request) -> dict[str, Any]:
    """Build secure cookie options for the current request."""
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": request.url.scheme == "https",
        "max_age": int(SESSION_TTL.total_seconds()),
        "path": "/",
    }


def get_user_by_username(username: str) -> dict[str, Any] | None:
    """Fetch an enabled or disabled user by username."""
    return db.fetch_one(
        """
        SELECT *
          FROM users
         WHERE username = ?
        """,
        (username,),
        db_path=USERS_DB_PATH,
    )


def get_user_from_session_token(token: str | None) -> dict[str, Any] | None:
    """Fetch a user from a valid non-expired browser session token."""
    if not token:
        return None

    now = sqlite_timestamp()
    token_hash = hash_session_token(token)
    with db.transaction(USERS_DB_PATH) as conn:
        row = db.fetch_one_on(
            conn,
            """
            SELECT u.*
              FROM user_sessions s
              JOIN users u ON u.id = s.user_id
             WHERE s.session_token_hash = ?
               AND s.revoked_at IS NULL
               AND s.expires_at > ?
               AND u.enabled = 1
            """,
            (token_hash, now),
        )
        if row is None:
            return None

        db.execute_on(
            conn,
            """
            UPDATE user_sessions
               SET last_seen_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
             WHERE session_token_hash = ?
            """,
            (token_hash,),
        )
        return db.row_to_dict(row)


def get_current_user(request: Request) -> dict[str, Any] | None:
    """Return the authenticated user attached to a request, if any."""
    user = getattr(request.state, "current_user", None)
    if user:
        return user
    return get_user_from_session_token(request.cookies.get(SESSION_COOKIE))


def record_login_event(
    username: str,
    event_type: str,
    request: Request,
    *,
    user_id: int | None = None,
    message: str | None = None,
) -> None:
    """Store an authentication event for audit purposes."""
    remote_addr = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    with db.transaction(USERS_DB_PATH) as conn:
        db.execute_on(
            conn,
            """
            INSERT INTO user_login_events (
                 user_id,
                 username,
                 event_type,
                 remote_addr,
                 user_agent,
                 message
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, event_type, remote_addr, user_agent, message),
        )


def register_failed_login(username: str, request: Request, user: dict[str, Any] | None = None) -> None:
    """Record a failed login attempt and increment the user counter when possible."""
    with db.transaction(USERS_DB_PATH) as conn:
        if user:
            db.execute_on(
                conn,
                """
                UPDATE users
                   SET failed_login_count = failed_login_count + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ?
                """,
                (user["id"],),
            )
        db.execute_on(
            conn,
            """
            INSERT INTO user_login_events (
                 user_id,
                 username,
                 event_type,
                 remote_addr,
                 user_agent,
                 message
            ) VALUES (?, ?, 'failed', ?, ?, ?)
            """,
            (
                user["id"] if user else None,
                username,
                request.client.host if request.client else None,
                request.headers.get("user-agent"),
                "Invalid username or password.",
            ),
        )


def create_session(user: dict[str, Any], request: Request, response: Response) -> None:
    """Create a browser session and attach it to the response cookie."""
    token = secrets.token_urlsafe(48)
    expires_at = sqlite_timestamp(utc_now() + SESSION_TTL)
    remote_addr = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    with db.transaction(USERS_DB_PATH) as conn:
        db.execute_on(
            conn,
            """
            INSERT INTO user_sessions (
                 user_id,
                 session_token_hash,
                 remote_addr,
                 user_agent,
                 expires_at,
                 last_seen_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (user["id"], hash_session_token(token), remote_addr, user_agent, expires_at),
        )
        db.execute_on(
            conn,
            """
            UPDATE users
               SET failed_login_count = 0,
                   last_login_at = CURRENT_TIMESTAMP,
                   last_login_ip = ?,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (remote_addr, user["id"]),
        )
        db.execute_on(
            conn,
            """
            INSERT INTO user_login_events (
                 user_id,
                 username,
                 event_type,
                 remote_addr,
                 user_agent,
                 message
            ) VALUES (?, ?, 'success', ?, ?, ?)
            """,
            (user["id"], user["username"], remote_addr, user_agent, "Login accepted."),
        )

    response.set_cookie(SESSION_COOKIE, token, **session_cookie_params(request))


def revoke_session(request: Request) -> None:
    """Revoke the current browser session when a token exists."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return

    with db.transaction(USERS_DB_PATH) as conn:
        db.execute_on(
            conn,
            """
            UPDATE user_sessions
               SET revoked_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
             WHERE session_token_hash = ?
            """,
            (hash_session_token(token),),
        )


def clear_session_cookie(response: Response) -> None:
    """Remove the browser session cookie from a response."""
    response.delete_cookie(SESSION_COOKIE, path="/")


def authenticate(username: str, password: str, request: Request) -> tuple[dict[str, Any] | None, str | None]:
    """Validate submitted credentials and return a user or an error message."""
    user = get_user_by_username(username)
    if not user or int(user["enabled"]) != 1:
        register_failed_login(username, request, user)
        return None, "Invalid username or password."

    locked_until = parse_sqlite_timestamp(user.get("locked_until"))
    if locked_until and locked_until > utc_now():
        record_login_event(username, "locked", request, user_id=user["id"], message="User is locked.")
        return None, "User is temporarily locked."

    if not verify_password(password, user["password_hash"]):
        register_failed_login(username, request, user)
        return None, "Invalid username or password."

    return user, None


def change_password(user: dict[str, Any], new_password: str) -> None:
    """Persist a new password and clear the first-login password change flag."""
    db.execute(
        """
        UPDATE users
           SET password_hash = ?,
               password_changed_at = CURRENT_TIMESTAMP,
               must_change_password = 0,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
        (hash_password(new_password), user["id"]),
        db_path=USERS_DB_PATH,
    )


async def enforce_authentication(request: Request, call_next: Any) -> Response:
    """Protect every web and API route except the authentication flow and static assets."""
    path = request.url.path

    if path in AUTH_FLOW_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return await call_next(request)

    user = get_user_from_session_token(request.cookies.get(SESSION_COOKIE))
    request.state.current_user = user
    if not user:
        return unauthorized_response(request)

    if int(user.get("must_change_password") or 0) == 1 and path != LOGOUT_PATH:
        if wants_json(request):
            return JSONResponse({"detail": "Password change required."}, status_code=403)
        return RedirectResponse(CHANGE_PASSWORD_PATH, status_code=303)

    return await call_next(request)
