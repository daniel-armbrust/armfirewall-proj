from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from web.dashboard import views as dashboard_views
from web.services.routingprotocols import views as routingprotocols_views


router = APIRouter()

PAGES = {
    "/armfirewall/ia": "FW Copilot",
    "/settings/users": "Users",
    "/settings/system": "Settings",
    "/network/interfaces": "Interfaces",
    "/network/neighbor-table": "Neighbor Table",
    "/network/policy-routing": "Policy Routing",
    "/network/qos": "QoS",
    "/routing/rip": "RIP",
    "/routing/ospf": "OSPF",
    "/routing/bgp": "BGP",
    "/monitoring/cpu-mem": "CPU & Mem",
    "/monitoring/network": "Network",
    "/monitoring/system": "System",
    "/monitoring/socket-states": "Socket States",
    "/monitoring/filesystem": "Filesystem",
    "/monitoring/disk": "Filesystem",
    "/monitoring/latency": "Latency",
    "/tools/ping": "Ping",
    "/tools/mtr": "MTR",
    "/tools/packet-capture": "Packet Capture",
    "/tools/traceroute": "Traceroute",
    "/services/status": "Status",
    "/services/link-failover": "Link Failover",
}


@router.get("/routing", response_class=HTMLResponse)
def routing_protocols(request: Request) -> HTMLResponse:
    """Render the Network / Routing Protocols page."""
    return routingprotocols_views.render_routing_protocols(request)


@router.get("/{section}/{page_name}", response_class=HTMLResponse)
def menu_page(request: Request, section: str, page_name: str) -> HTMLResponse:
    """Render a generic menu page when no custom view exists."""
    path = f"/{section}/{page_name}"
    title = PAGES.get(path)
    if title is None:
        raise HTTPException(status_code=404, detail="Page not found.")

    return dashboard_views.render_menu_page(request, title, section)


@router.get("/{section}/{group_name}/{page_name}", response_class=HTMLResponse)
def nested_menu_page(request: Request, section: str, group_name: str, page_name: str) -> HTMLResponse:
    """Render a generic nested menu page when no custom view exists."""
    path = f"/{section}/{group_name}/{page_name}"
    title = PAGES.get(path)
    if title is None:
        raise HTTPException(status_code=404, detail="Page not found.")

    return dashboard_views.render_menu_page(request, title, f"{section}/{group_name}")
