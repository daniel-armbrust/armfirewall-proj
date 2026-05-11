from __future__ import annotations

import subprocess
from datetime import datetime
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import HTMLResponse

from web.dashboard import views as dashboard_views


NEIGHBOR_STATES = {
    "INCOMPLETE",
    "REACHABLE",
    "STALE",
    "DELAY",
    "PROBE",
    "FAILED",
    "NOARP",
    "PERMANENT",
}


def address_family(address: str) -> str:
    """Return the address family for one neighbor address."""
    return "ipv6" if ":" in address else "ipv4"


def parse_neighbor_line(line: str) -> Optional[dict[str, str]]:
    """Parse one line from ip neighbor show output."""
    parts = line.split()
    if not parts:
        return None

    address = parts[0]
    iface = "-"
    mac_address = "-"
    state = "UNKNOWN"
    flags: list[str] = []

    index = 1
    while index < len(parts):
        token = parts[index]
        next_value = parts[index + 1] if index + 1 < len(parts) else ""

        if token == "dev" and next_value:
            iface = next_value
            index += 2
            continue
        if token == "lladdr" and next_value:
            mac_address = next_value
            index += 2
            continue
        if token.upper() in NEIGHBOR_STATES:
            state = token.upper()
            index += 1
            continue
        if token in {"router", "extern_learn", "managed", "use", "proxy"}:
            flags.append(token)
            index += 1
            continue
        if token in {"used", "confirmed", "updated", "probes", "ref"} and next_value:
            flags.append(f"{token}={next_value}")
            index += 2
            continue

        index += 1

    return {
        "addr_family": address_family(address),
        "ip_address": address,
        "mac_address": mac_address,
        "iface": iface,
        "state": state,
        "flags": ", ".join(flags) if flags else "-",
        "raw": line,
        "source": "ip-neighbor",
    }


def read_ip_neighbors() -> list[dict[str, str]]:
    """Read kernel neighbor entries with iproute2."""
    result = subprocess.run(
        ["ip", "neighbor", "show"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ip neighbor show failed.")

    rows: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        row = parse_neighbor_line(line)
        if row:
            rows.append(row)
    return rows


def get_neighbor_table() -> dict[str, Any]:
    """Return the current operating system neighbor table."""
    entries = read_ip_neighbors()
    entries.sort(key=lambda item: (item["addr_family"], item["iface"], item["ip_address"]))
    interfaces = sorted({entry["iface"] for entry in entries if entry["iface"] and entry["iface"] != "-"})
    reachable_states = {"REACHABLE", "STALE", "DELAY", "PROBE", "PERMANENT", "NOARP"}
    reachable = sum(1 for entry in entries if entry["state"] in reachable_states)
    return {
        "summary": {
            "entries": len(entries),
            "interfaces": len(interfaces),
            "reachable": reachable,
            "ipv4": sum(1 for entry in entries if entry["addr_family"] == "ipv4"),
            "ipv6": sum(1 for entry in entries if entry["addr_family"] == "ipv6"),
            "source": "ip-neighbor",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "entries": entries,
    }


def render_neighbor_table(request: Request) -> HTMLResponse:
    """Render the Network / Neighbor Table page."""
    return dashboard_views.templates.TemplateResponse(
        request,
        "network/neighbor_table.html",
        context=dashboard_views.page_context(request, "Neighbor Table"),
    )
