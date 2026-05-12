from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core import db
from core import iface as iface_module


ROOT_DIR = Path(__file__).resolve().parents[3]
LINKFAILOVER_DB_PATH = ROOT_DIR / "db" / "linkfailover.db"
WORK_REQUEST_DB_PATH = ROOT_DIR / "db" / "work-requests.db"
templates = Jinja2Templates(directory=[ROOT_DIR / "web" / "templates", ROOT_DIR / "templates"])
TARGET_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for the Link Failover page."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def render_linkfailover(request: Request) -> HTMLResponse:
    """Render the Link Failover service template."""
    return templates.TemplateResponse(
        request,
        "services/linkfailover.html",
        context=page_context(request, "Link Failover"),
    )


def require_linkfailover_db() -> None:
    """Raise an HTTP error when linkfailover.db is not ready."""
    if not LINKFAILOVER_DB_PATH.exists():
        raise HTTPException(status_code=503, detail="Link Failover database is not ready.")


def none_if_blank(value: Any) -> str | None:
    """Normalize blank strings to None."""
    text = str(value or "").strip()
    return text or None


def validate_int(payload: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    """Validate and clamp one integer payload field."""
    try:
        value = int(payload.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number.") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}.")
    return value


def validate_latency(payload: dict[str, Any]) -> float | None:
    """Validate the optional maximum latency threshold."""
    raw_value = payload.get("max_latency_ms")
    if raw_value in (None, ""):
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_latency_ms must be a number.") from exc
    if value < 0:
        raise ValueError("max_latency_ms must be greater than or equal to zero.")
    return value


def validate_target(value: Any) -> str:
    """Validate one ping target hostname or address."""
    target = str(value or "").strip()
    if not target:
        raise ValueError("target is required.")
    if not TARGET_RE.match(target):
        raise ValueError("target contains invalid characters.")
    return target


def iface_names() -> set[str]:
    """Return known interface names from iface.db."""
    try:
        return {str(item["name"]) for item in iface_module.get_interfaces().get("interfaces", [])}
    except (FileNotFoundError, db.DatabaseError):
        return set()


def validate_link_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate one Link Failover link payload."""
    names = iface_names()
    iface = str(payload.get("iface") or "").strip()
    if not iface:
        raise ValueError("iface is required.")
    if names and iface not in names:
        raise ValueError("iface must be one of the interfaces known by ArmFirewall.")
    return {
        "iface": iface,
        "priority": validate_int(payload, "priority", 100, 1, 999),
    }


def interfaces() -> list[dict[str, Any]]:
    """Return GUI interface choices from iface.db."""
    return iface_module.get_interfaces().get("interfaces", [])


def get_service_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent Link Failover service work requests."""
    query = """
        SELECT id, request_uid, status, category_name, action_name,
               payload_json, error_message, created_at, updated_at
        FROM work_requests
        WHERE category_name = 'SERVICE_MANAGEMENT.SERVICE_CONTROL'
        ORDER BY id DESC
        LIMIT ?
    """
    rows: list[dict[str, Any]] = []
    try:
        with db.connection(WORK_REQUEST_DB_PATH) as conn:
            raw_rows = db.fetch_all_on(conn, query, (limit,))
    except FileNotFoundError:
        raw_rows = []

    for row in raw_rows:
        try:
            payload = json.loads(str(row.get("payload_json") or "{}"))
        except json.JSONDecodeError:
            payload = {}
        if payload.get("service_name") != "armfirewall-linkfailover":
            continue
        item = dict(row)
        item["service_name"] = payload.get("service_name", "-")
        item.pop("payload_json", None)
        rows.append(item)
    return {"requests": rows}


def get_config() -> dict[str, Any]:
    """Return Link Failover settings, links, events, and interface choices."""
    require_linkfailover_db()
    with db.connection(LINKFAILOVER_DB_PATH) as conn:
        settings = db.fetch_one_on(
            conn,
            """
            SELECT id, target, timeout_seconds, attempts, interval_seconds,
                   max_latency_ms, check_interval_seconds, current_iface,
                   last_route_change_at, last_checked_at, updated_at
            FROM linkfailover_settings
            WHERE id = 1
            """,
        )
        links = db.fetch_all_on(
            conn,
            """
            SELECT id, iface, priority,
                   status, last_latency_ms, last_error, last_checked_at,
                   success_count, fail_count, created_at, updated_at
            FROM linkfailover_links
            ORDER BY priority ASC, id ASC
            """,
        )
        events = db.fetch_all_on(
            conn,
            """
            SELECT id, link_id, event_type, message, details_json, created_at
            FROM linkfailover_events
            ORDER BY id DESC
            LIMIT 30
            """,
        )

    healthy_links = sum(1 for item in links if item.get("status") == "healthy")
    return {
        "settings": dict(settings) if settings is not None else {},
        "summary": {
            "links": len(links),
            "healthy_links": healthy_links,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "links": links,
        "events": events,
        "interfaces": interfaces(),
    }


def add_event(
    conn: db.Connection,
    event_type: str,
    message: str,
    *,
    link_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append one Link Failover GUI or daemon event."""
    db.execute_on(
        conn,
        """
        INSERT INTO linkfailover_events (link_id, event_type, message, details_json)
        VALUES (?, ?, ?, ?)
        """,
        (link_id, event_type, message, json.dumps(details or {}, sort_keys=True)),
    )


def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Update Link Failover global daemon settings."""
    require_linkfailover_db()
    target = validate_target(payload.get("target"))
    timeout_seconds = validate_int(payload, "timeout_seconds", 3, 1, 60)
    attempts = validate_int(payload, "attempts", 3, 1, 20)
    interval_seconds = validate_int(payload, "interval_seconds", 1, 0, 3600)
    max_latency_ms = validate_latency(payload)
    interval = validate_int(payload, "check_interval_seconds", 10, 1, 86400)
    with db.transaction(LINKFAILOVER_DB_PATH) as conn:
        db.execute_on(
            conn,
            """
            UPDATE linkfailover_settings
            SET target = ?,
                timeout_seconds = ?,
                attempts = ?,
                interval_seconds = ?,
                max_latency_ms = ?,
                check_interval_seconds = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (target, timeout_seconds, attempts, interval_seconds, max_latency_ms, interval),
        )
        add_event(
            conn,
            "config",
            "Link Failover settings were updated.",
            details={
                "target": target,
                "timeout_seconds": timeout_seconds,
                "attempts": attempts,
                "interval_seconds": interval_seconds,
                "max_latency_ms": max_latency_ms,
                "check_interval_seconds": interval,
            },
        )
    return {"status": "ok"}


def create_link(payload: dict[str, Any]) -> dict[str, Any]:
    """Create one Link Failover monitored link."""
    require_linkfailover_db()
    try:
        link = validate_link_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        with db.transaction(LINKFAILOVER_DB_PATH) as conn:
            row = db.fetch_one_on(conn, "SELECT COUNT(*) AS total FROM linkfailover_links")
            if row is not None and int(row["total"] or 0) >= 2:
                raise HTTPException(status_code=400, detail="Link Failover supports exactly two links.")
            cursor = db.execute_on(
                conn,
                """
                INSERT INTO linkfailover_links (
                    iface, priority
                )
                VALUES (?, ?)
                """,
                (
                    link["iface"],
                    link["priority"],
                ),
            )
            link_id = int(cursor.lastrowid)
            add_event(
                conn,
                "config",
                f"Link Failover interface {link['iface']} was added.",
                link_id=link_id,
                details={"iface": link["iface"], "priority": link["priority"]},
            )
    except db.DatabaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "id": link_id}


def update_link(link_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update one Link Failover monitored link."""
    require_linkfailover_db()
    try:
        link = validate_link_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with db.transaction(LINKFAILOVER_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            UPDATE linkfailover_links
            SET iface = ?, priority = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                link["iface"],
                link["priority"],
                link_id,
            ),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Link Failover entry not found.")
        add_event(
            conn,
            "config",
            f"Link Failover interface {link['iface']} was updated.",
            link_id=link_id,
            details={"iface": link["iface"], "priority": link["priority"]},
        )
    return {"status": "ok", "id": link_id}


def delete_link(link_id: int) -> dict[str, Any]:
    """Delete one Link Failover monitored link."""
    require_linkfailover_db()
    with db.transaction(LINKFAILOVER_DB_PATH) as conn:
        row = db.fetch_one_on(conn, "SELECT iface FROM linkfailover_links WHERE id = ?", (link_id,))
        cursor = db.execute_on(conn, "DELETE FROM linkfailover_links WHERE id = ?", (link_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Link Failover entry not found.")
        iface = str(row["iface"]) if row is not None else str(link_id)
        add_event(
            conn,
            "config",
            f"Link Failover interface {iface} was deleted.",
            details={"iface": iface, "link_id": link_id},
        )
    return {"status": "ok", "id": link_id}
