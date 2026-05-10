from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


ROOT_DIR = Path(__file__).resolve().parents[2]
CONF_PATH = ROOT_DIR / "conf" / "armfw.conf"
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
    """Return the first LAN interface configured in armfw.conf."""
    if not CONF_PATH.exists():
        return ""

    for raw_line in CONF_PATH.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "lan_iface":
            continue

        normalized = value.replace(",", " ")
        parts = [part.strip() for part in normalized.split() if part.strip()]
        return parts[0] if parts else ""

    return ""


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
