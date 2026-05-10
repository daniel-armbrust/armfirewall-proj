from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web.services.dhcp import dhcp as services_dhcp_views
from web.services.dns import dns as services_dns_views
from web.services.proxy import proxy as services_proxy_views


router = APIRouter()


@router.get("/services/dhcp", response_class=HTMLResponse)
def services_dhcp(request: Request) -> HTMLResponse:
    """Render the DHCP service page."""
    return services_dhcp_views.render_dhcp(request)


@router.get("/services/dns", response_class=HTMLResponse)
def services_dns(request: Request) -> HTMLResponse:
    """Render the DNS service page."""
    return services_dns_views.render_dns(request)


@router.get("/services/proxy", response_class=HTMLResponse)
def services_proxy(request: Request) -> HTMLResponse:
    """Render the Proxy service page."""
    return services_proxy_views.render_proxy(request)
