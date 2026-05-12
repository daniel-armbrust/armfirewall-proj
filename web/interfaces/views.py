from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core import db

ROOT_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=[ROOT_DIR / "web" / "templates", ROOT_DIR / "templates"])


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for interface pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def render_interfaces(request: Request) -> HTMLResponse:
    """Render the interface inventory page."""
    return templates.TemplateResponse(
        request,
        "interfaces/interfaces.html",
        context=page_context(request, "Interfaces"),
    )


def first_lan_iface() -> str:
    """Return the first protected LAN interface persisted in iface.db."""
    try:
        row = db.fetch_one(
            """
            SELECT name
            FROM ifaces
            WHERE role = 'LAN'
              AND protected = 1
            ORDER BY id
            LIMIT 1
            """
        )
    except (FileNotFoundError, db.DatabaseError):
        return ""
    return str(row["name"]) if row else ""


def render_interface_edit(request: Request, iface_name: str) -> HTMLResponse:
    """Render the edit page for one network interface."""
    protected_readonly = iface_name == first_lan_iface()

    return templates.TemplateResponse(
        request,
        "interfaces/interface_edit.html",
        context=page_context(request, f"Edit {iface_name}")
        | {
            "iface_name": iface_name,
            "protected_readonly": protected_readonly,
        },
    )
