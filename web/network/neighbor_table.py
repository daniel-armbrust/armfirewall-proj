from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from core import db
from core.constants import NETWORK_DB_PATH
from web.dashboard import views as dashboard_views


def get_neighbor_table() -> dict[str, Any]:
    """Return the latest persisted kernel neighbor-cache snapshot."""
    with db.connection(NETWORK_DB_PATH) as conn:
        snapshot = db.fetch_one_on(
            conn,
            "SELECT source, collected_at FROM neighbor_snapshot WHERE id = 1",
        )
        rows = db.fetch_all_on(
            conn,
            """SELECT addr_family, ip_address, mac_address, iface_name, state, flags,
                      raw_entry
               FROM neighbor_entry
               WHERE snapshot_id = 1
               ORDER BY addr_family, iface_name, ip_address""",
        )
    if snapshot is None:
        raise RuntimeError("Neighbor snapshot is not available.")
    entries = [
        {
            "addr_family": str(row["addr_family"]),
            "ip_address": str(row["ip_address"]),
            "mac_address": str(row["mac_address"] or "-"),
            "iface": str(row["iface_name"] or "-"),
            "state": str(row["state"]),
            "flags": str(row["flags"] or "-"),
            "raw": str(row["raw_entry"]),
            "source": str(snapshot["source"]),
        }
        for row in rows
    ]
    reachable_states = {"REACHABLE", "STALE", "DELAY", "PROBE", "PERMANENT", "NOARP"}
    return {
        "summary": {
            "entries": len(entries),
            "interfaces": len(
                {item["iface"] for item in entries if item["iface"] != "-"}
            ),
            "reachable": sum(item["state"] in reachable_states for item in entries),
            "ipv4": sum(item["addr_family"] == "ipv4" for item in entries),
            "ipv6": sum(item["addr_family"] == "ipv6" for item in entries),
            "source": str(snapshot["source"]),
            "updated_at": str(snapshot["collected_at"]),
        },
        "entries": entries,
    }


def render_neighbor_table(request: Request) -> HTMLResponse:
    """Render the Network / Neighbor Table page."""
    return dashboard_views.templates.TemplateResponse(request, "network/neighbor_table.html", context=dashboard_views.page_context(request, "Neighbor Table"))
