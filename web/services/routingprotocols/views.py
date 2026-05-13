from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from web.dashboard import views as dashboard_views
from web.services.routingprotocols import api as routingprotocols_api


def render_routing_protocols(request: Request) -> HTMLResponse:
    """Render the Network / Routing Protocols page."""
    return dashboard_views.templates.TemplateResponse(
        request,
        "network/routing_protocols.html",
        context=dashboard_views.page_context(request, "Routing Protocols")
        | {
            "section": "network",
            "bird_installed": routingprotocols_api.bird_service_installed(),
        },
    )
