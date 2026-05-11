from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


ROOT_DIR = Path(__file__).resolve().parents[3]
SUPERVISOR_CONF = ROOT_DIR / "conf" / "supervisord.conf"
templates = Jinja2Templates(directory=[ROOT_DIR / "web" / "templates", ROOT_DIR / "templates"])


def proxy_service_installed() -> bool:
    """Return whether the Squid proxy service is registered in supervisord."""
    if not SUPERVISOR_CONF.exists():
        return False
    return "[program:armfirewall-squid]" in SUPERVISOR_CONF.read_text(encoding="utf-8")


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for service pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def render_proxy(request: Request) -> HTMLResponse:
    """Render the Proxy service template."""
    if not proxy_service_installed():
        raise HTTPException(status_code=404, detail="Proxy service is not installed.")
    return templates.TemplateResponse(
        request,
        "services/proxy.html",
        context=page_context(request, "Proxy"),
    )
