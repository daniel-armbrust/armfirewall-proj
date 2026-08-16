from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from web.services.dnsmasq.views import page_context, templates


def render_adguardhome(request: Request) -> HTMLResponse:
    """Render the AdGuard Home configuration page."""
    return templates.TemplateResponse(
        request,
        "services/adguardhome.html",
        context=page_context(request, "AdGuard Home"),
    )
