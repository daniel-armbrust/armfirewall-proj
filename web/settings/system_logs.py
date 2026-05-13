from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web import auth
from core import db
from core.constants import LOG_DB_PATH
from web.constants import TEMPLATE_DIR


templates = Jinja2Templates(directory=TEMPLATE_DIR)
LOGS_DB_PATH = LOG_DB_PATH


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for ArmFirewall pages."""
    current_user = auth.get_current_user(request) or {}
    return {
        "request": request,
        "title": title,
        "user_name": current_user.get("username", "admin"),
        "current_path": request.url.path,
    }


def render_system_logs(request: Request) -> HTMLResponse:
    """Render the ArmFirewall system logs page."""
    return templates.TemplateResponse(
        request,
        "settings/system_logs.html",
        context=page_context(request, "System Logs"),
    )


def normalize_limit(value: Any) -> int:
    """Normalize the requested log row limit."""
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 200
    return max(1, min(limit, 1000))


def list_logs(limit: int = 200) -> dict[str, Any]:
    """Return recent ArmFirewall log records."""
    rows = db.fetch_all(
        """
        SELECT id, source, level, message, created_at
          FROM logs
         ORDER BY id DESC
         LIMIT ?
        """,
        (normalize_limit(limit),),
        db_path=LOGS_DB_PATH,
    )
    summary = {
        "rows": len(rows),
        "errors": sum(1 for row in rows if row["level"] in {"ERROR", "FATAL"}),
        "warnings": sum(1 for row in rows if row["level"] == "WARNING"),
        "last_id": rows[0]["id"] if rows else 0,
        "updated_at": rows[0]["created_at"] if rows else "-",
    }
    return {"summary": summary, "logs": rows}
