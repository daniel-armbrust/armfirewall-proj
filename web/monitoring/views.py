from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core import db


ROOT_DIR = Path(__file__).resolve().parents[2]
RRD_IMG_DIR = ROOT_DIR / "rrd" / "img"
LATENCY_DB_PATH = ROOT_DIR / "db" / "latency.db"
IFACE_DB_PATH = ROOT_DIR / "db" / "iface.db"
templates = Jinja2Templates(directory=[ROOT_DIR / "web" / "templates", ROOT_DIR / "templates"])

CPU_MEM_GRAPHS = [
    {
        "id": "kern-cpu",
        "title": "Kernel CPU",
        "description": "CPU states from kern.rrd",
        "filename": "kern-cpu.png",
        "rrd": "kern.rrd",
    },
    {
        "id": "loadavg-load",
        "title": "Load Average",
        "description": "System load from loadavg.rrd",
        "filename": "loadavg-load.png",
        "rrd": "loadavg.rrd",
    },
    {
        "id": "mem-memory",
        "title": "Memory",
        "description": "Memory counters from mem.rrd",
        "filename": "mem-memory.png",
        "rrd": "mem.rrd",
    },
    {
        "id": "procstatus-processes",
        "title": "Processes",
        "description": "Process states from procstatus.rrd",
        "filename": "procstatus-processes.png",
        "rrd": "procstatus.rrd",
    },
]

SYSTEM_GRAPHS = [
    {
        "id": "uptime-uptime",
        "title": "Uptime",
        "description": "System uptime from uptime.rrd",
        "filename": "uptime-uptime.png",
        "rrd": "uptime.rrd",
    },
    {
        "id": "entropy-entropy",
        "title": "Entropy",
        "description": "Kernel entropy from entropy.rrd",
        "filename": "entropy-entropy.png",
        "rrd": "entropy.rrd",
    },
    {
        "id": "kern-context",
        "title": "Context Switches",
        "description": "Context switches and forks from kern.rrd",
        "filename": "kern-context.png",
        "rrd": "kern.rrd",
    },
    {
        "id": "kern-usage",
        "title": "Kernel Usage",
        "description": "Dentry, file and inode usage from kern.rrd",
        "filename": "kern-usage.png",
        "rrd": "kern.rrd",
    },
]

SOCKET_STATE_GRAPHS = [
    {
        "id": "netstat-ipv4-tcp",
        "title": "IPv4 TCP States",
        "description": "IPv4 TCP socket state counters from netstat.rrd",
        "filename": "netstat-ipv4-tcp.png",
        "rrd": "netstat.rrd",
    },
    {
        "id": "netstat-ipv6-tcp",
        "title": "IPv6 TCP States",
        "description": "IPv6 TCP socket state counters from netstat.rrd",
        "filename": "netstat-ipv6-tcp.png",
        "rrd": "netstat.rrd",
    },
    {
        "id": "netstat-tcp-closing-timewait",
        "title": "TCP Closing / Time Wait",
        "description": "TCP CLOSING and TIME_WAIT states from netstat.rrd",
        "filename": "netstat-tcp-closing-timewait.png",
        "rrd": "netstat.rrd",
    },
    {
        "id": "netstat-tcp-wait-unknown",
        "title": "TCP Wait / Unknown",
        "description": "TCP CLOSE_WAIT, LAST_ACK and UNKNOWN states from netstat.rrd",
        "filename": "netstat-tcp-wait-unknown.png",
        "rrd": "netstat.rrd",
    },
    {
        "id": "netstat-udp",
        "title": "UDP Sockets",
        "description": "IPv4 and IPv6 UDP socket counters from netstat.rrd",
        "filename": "netstat-udp.png",
        "rrd": "netstat.rrd",
    },
]

GRAPH_PERIODS = [
    {"id": "daily", "label": "Daily", "suffix": ""},
    {"id": "weekly", "label": "Weekly", "suffix": "-weekly"},
    {"id": "monthly", "label": "Monthly", "suffix": "-monthly"},
    {"id": "yearly", "label": "Yearly", "suffix": "-yearly"},
]
NETWORK_GRAPH_TYPES = [
    {
        "suffix": "traffic",
        "title": "Traffic",
        "description": "Interface bandwidth rates",
    },
    {
        "suffix": "packets",
        "title": "Packets",
        "description": "Interface packet rates",
    },
    {
        "suffix": "errors",
        "title": "Errors",
        "description": "Interface error rates",
    },
]
FILESYSTEM_GRAPH_TYPES = [
    {
        "suffix": "usage",
        "title": "Usage",
        "description": "Filesystem usage percentage",
    },
    {
        "suffix": "inodes",
        "title": "Inodes",
        "description": "Inode usage percentage",
    },
    {
        "suffix": "io-ops",
        "title": "I/O Activity",
        "description": "Reads and writes per second",
    },
    {
        "suffix": "io-time",
        "title": "I/O Time",
        "description": "Disk I/O time per second",
    },
]
LATENCY_GRAPH_TYPES = [
    {
        "suffix": "latency",
        "title": "Latency",
        "description": "ICMP round-trip latency min, average and max",
    },
    {
        "suffix": "loss",
        "title": "Packet Loss",
        "description": "ICMP packet loss percentage",
    },
]


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for monitoring pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def period_filename(filename: str, suffix: str) -> str:
    """Return one graph filename for a period suffix."""
    path = Path(filename)
    return f"{path.stem}{suffix}{path.suffix}"


def sanitize_iface_name(iface_name: str) -> str:
    """Return the graph-safe interface name used by monitord."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", iface_name)


def sanitize_mount_name(mountpoint: str) -> str:
    """Return the graph-safe mount name used by monitord."""
    if mountpoint == "/":
        return "root"
    sanitized = mountpoint.strip("/").replace("/", "_")
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", sanitized)
    return sanitized or "unknown"


def decode_mount_field(value: str) -> str:
    """Decode octal escapes used by Linux mountinfo fields."""
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def period_payload(filename: str, period: dict[str, str]) -> dict[str, Any]:
    """Return one period image metadata object."""
    image_name = period_filename(filename, period["suffix"])
    path = RRD_IMG_DIR / image_name
    exists = path.exists()
    updated_at = ""
    updated_label = ""
    if exists:
        updated_at = path.stat().st_mtime_ns
        updated_label = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": period["id"],
        "label": period["label"],
        "filename": image_name,
        "exists": exists,
        "updated_at": updated_at,
        "updated_label": updated_label,
        "image_url": f"/rrd-img/{image_name}",
    }


def graph_payload(graph: dict[str, str]) -> dict[str, Any]:
    """Return graph metadata with current file state by period."""
    periods = {period["id"]: period_payload(graph["filename"], period) for period in GRAPH_PERIODS}
    current_period = periods["daily"]
    return {
        **graph,
        "exists": current_period["exists"],
        "updated_at": current_period["updated_at"],
        "image_url": current_period["image_url"],
        "periods": periods,
    }


def get_cpu_mem_graphs() -> dict[str, Any]:
    """Return CPU and memory graph metadata for the frontend."""
    graphs = [graph_payload(graph) for graph in CPU_MEM_GRAPHS]
    return {"graphs": graphs, "periods": GRAPH_PERIODS}


def get_system_graphs() -> dict[str, Any]:
    """Return system graph metadata for the frontend."""
    graphs = [graph_payload(graph) for graph in SYSTEM_GRAPHS]
    return {"graphs": graphs, "periods": GRAPH_PERIODS}


def get_socket_state_graphs() -> dict[str, Any]:
    """Return socket state graph metadata for the frontend."""
    graphs = [graph_payload(graph) for graph in SOCKET_STATE_GRAPHS]
    return {"graphs": graphs, "periods": GRAPH_PERIODS}


def read_monitored_interfaces() -> list[dict[str, Any]]:
    """Read monitored interfaces from iface.db for network graphs."""
    rows = db.fetch_all(
        """
        SELECT name, role, description
        FROM ifaces
        ORDER BY
            CASE role
                WHEN 'LAN' THEN 1
                WHEN 'WAN' THEN 2
                ELSE 3
            END,
            name
        """
    )
    return [db.row_to_dict(row) for row in rows if row.get("name")]


def interface_payload(iface: dict[str, Any]) -> dict[str, str]:
    """Return frontend metadata for one monitored interface."""
    name = str(iface.get("name") or "")
    role = str(iface.get("role") or "UNKNOWN")
    description = str(iface.get("description") or "")
    return {
        "name": name,
        "safe_name": sanitize_iface_name(name),
        "role": role,
        "description": description,
        "label": f"{name} ({role}) - {description}",
    }


def network_graphs_for_iface(iface: dict[str, Any]) -> list[dict[str, str]]:
    """Build graph descriptors for one monitored interface."""
    iface_name = str(iface["name"])
    safe_name = sanitize_iface_name(iface_name)
    role = str(iface.get("role") or "UNKNOWN")
    description = str(iface.get("description") or "")
    graphs: list[dict[str, str]] = []
    for graph_type in NETWORK_GRAPH_TYPES:
        suffix = graph_type["suffix"]
        graphs.append(
            {
                "id": f"{safe_name}-{suffix}",
                "title": f"{iface_name} {graph_type['title']}",
                "description": f"{graph_type['description']} / role={role}",
                "filename": f"{safe_name}-{suffix}.png",
                "rrd": f"{safe_name}.rrd",
                "iface_name": iface_name,
                "iface_safe_name": safe_name,
                "iface_role": role,
                "iface_description": description,
            }
        )
    return graphs


def get_network_graphs() -> dict[str, Any]:
    """Return network interface graph metadata for the frontend."""
    graphs: list[dict[str, Any]] = []
    interfaces = read_monitored_interfaces()
    for iface in interfaces:
        graphs.extend(graph_payload(graph) for graph in network_graphs_for_iface(iface))
    return {
        "graphs": graphs,
        "interfaces": [interface_payload(iface) for iface in interfaces],
        "periods": GRAPH_PERIODS,
    }


def read_current_filesystems() -> dict[str, dict[str, str]]:
    """Read current mounted filesystems and map them by safe graph name."""
    mountinfo = Path("/proc/self/mountinfo")
    filesystems: dict[str, dict[str, str]] = {}
    if not mountinfo.exists():
        return filesystems

    for line in mountinfo.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if "-" not in fields or len(fields) < 10:
            continue
        separator = fields.index("-")
        if separator + 2 >= len(fields):
            continue
        mountpoint = decode_mount_field(fields[4])
        fstype = fields[separator + 1]
        source = decode_mount_field(fields[separator + 2])
        safe_name = sanitize_mount_name(mountpoint)
        filesystems[safe_name] = {
            "safe_name": safe_name,
            "mountpoint": mountpoint,
            "fstype": fstype,
            "source": source,
            "label": f"{mountpoint} ({fstype}) - {source}",
        }
    return filesystems


def filesystem_label_from_safe_name(safe_name: str) -> str:
    """Return a readable filesystem label when mountinfo is unavailable."""
    if safe_name == "root":
        return "/"
    return "/" + safe_name.replace("_", "/")


def read_monitored_filesystems() -> list[dict[str, str]]:
    """Read filesystem graph targets from fs RRD files."""
    current_filesystems = read_current_filesystems()
    filesystems: list[dict[str, str]] = []
    for rrd_path in sorted(RRD_IMG_DIR.parent.glob("fs-*.rrd")):
        safe_name = rrd_path.stem.removeprefix("fs-")
        filesystem = current_filesystems.get(safe_name)
        if filesystem is None:
            mountpoint = filesystem_label_from_safe_name(safe_name)
            filesystem = {
                "safe_name": safe_name,
                "mountpoint": mountpoint,
                "fstype": "unknown",
                "source": "fs.rrd",
                "label": f"{mountpoint} (unknown) - fs.rrd",
            }
        filesystems.append(filesystem)
    return sorted(filesystems, key=lambda filesystem: (filesystem["mountpoint"] != "/", filesystem["mountpoint"]))


def filesystem_graphs_for_mount(filesystem: dict[str, str]) -> list[dict[str, str]]:
    """Build graph descriptors for one monitored filesystem."""
    safe_name = filesystem["safe_name"]
    mountpoint = filesystem["mountpoint"]
    fstype = filesystem.get("fstype") or "unknown"
    source = filesystem.get("source") or "unknown"
    graphs: list[dict[str, str]] = []
    for graph_type in FILESYSTEM_GRAPH_TYPES:
        suffix = graph_type["suffix"]
        graphs.append(
            {
                "id": f"fs-{safe_name}-{suffix}",
                "title": f"{mountpoint} {graph_type['title']}",
                "description": f"{graph_type['description']} / type={fstype}",
                "filename": f"fs-{safe_name}-{suffix}.png",
                "rrd": f"fs-{safe_name}.rrd",
                "filesystem_safe_name": safe_name,
                "filesystem_mountpoint": mountpoint,
                "filesystem_fstype": fstype,
                "filesystem_source": source,
            }
        )
    return graphs


def get_filesystem_graphs() -> dict[str, Any]:
    """Return filesystem graph metadata for the frontend."""
    graphs: list[dict[str, Any]] = []
    filesystems = read_monitored_filesystems()
    for filesystem in filesystems:
        graphs.extend(graph_payload(graph) for graph in filesystem_graphs_for_mount(filesystem))
    return {
        "graphs": graphs,
        "filesystems": filesystems,
        "periods": GRAPH_PERIODS,
    }


def latency_label_from_safe_name(safe_name: str) -> str:
    """Return a readable latency target label from its safe name."""
    return safe_name.replace("_", " ").replace("-", " ")


def latency_safe_name(iface: str, target: str) -> str:
    """Return the graph-safe name for one configured latency target."""
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{iface}-{target}".strip())
    return safe_name.strip("_") or "target"


def read_interface_tooltips() -> dict[str, str]:
    """Read interface details and render tooltip text by interface name."""
    if not IFACE_DB_PATH.exists():
        return {}

    try:
        interfaces = db.fetch_all(
            """
            SELECT id, name, role, description, mac_address, mtu, is_actived, speed_mbps, duplex
            FROM ifaces
            ORDER BY name
            """,
            db_path=IFACE_DB_PATH,
        )
        addresses = db.fetch_all(
            """
            SELECT iface_id, addr_family, addr, prefixlen
            FROM addresses
            ORDER BY addr_family, addr
            """,
            db_path=IFACE_DB_PATH,
        )
    except db.DatabaseError:
        return {}

    addresses_by_iface: dict[int, list[str]] = {}
    for address in addresses:
        iface_id = int(address.get("iface_id") or 0)
        family = str(address.get("addr_family") or "").upper()
        addr = str(address.get("addr") or "")
        prefixlen = str(address.get("prefixlen") or "")
        if iface_id and addr:
            addresses_by_iface.setdefault(iface_id, []).append(f"{family} {addr}/{prefixlen}")

    tooltips: dict[str, str] = {}
    for iface in interfaces:
        iface_id = int(iface.get("id") or 0)
        name = str(iface.get("name") or "")
        if not name:
            continue
        state = "UP" if int(iface.get("is_actived") or 0) == 1 else "DOWN"
        lines = [
            f"Interface: {name}",
            f"Role: {iface.get('role') or 'UNKNOWN'}",
            f"Description: {iface.get('description') or '-'}",
            f"MAC: {iface.get('mac_address') or '-'}",
            f"MTU: {iface.get('mtu') or '-'}",
            f"State: {state}",
            f"Speed: {iface.get('speed_mbps') or 0} Mb/s",
            f"Duplex: {iface.get('duplex') or 'unknown'}",
        ]
        if addresses_by_iface.get(iface_id):
            lines.append(f"Addresses: {', '.join(addresses_by_iface[iface_id])}")
        tooltips[name] = "\n".join(lines)
    return tooltips


def latency_target_payload(row: dict[str, Any], interface_tooltips: dict[str, str] | None = None) -> dict[str, Any]:
    """Return frontend metadata for one configured latency target."""
    iface = str(row.get("iface") or "")
    target = str(row.get("target") or "")
    safe_name = latency_safe_name(iface, target)
    interface_tooltips = interface_tooltips if interface_tooltips is not None else read_interface_tooltips()
    return {
        **row,
        "safe_name": safe_name,
        "name": safe_name,
        "label": f"{target} ({iface})",
        "rrd": f"latency-{safe_name}.rrd",
        "interface_tooltip": interface_tooltips.get(iface, f"Interface: {iface}\nDetails unavailable"),
    }


def read_configured_latency_targets() -> list[dict[str, Any]]:
    """Read configured ping latency targets from latency.db."""
    if not LATENCY_DB_PATH.exists():
        return []

    try:
        rows = db.fetch_all(
            """
            SELECT id, iface, target, count, timeout, enabled, created_at, updated_at
            FROM latency_targets
            ORDER BY iface, target
            """,
            db_path=LATENCY_DB_PATH,
        )
        interface_tooltips = read_interface_tooltips()
        return [latency_target_payload(row, interface_tooltips) for row in rows]
    except db.DatabaseError:
        return []


def latency_target_or_none(target_id: int) -> dict[str, Any] | None:
    """Return one configured latency target by id."""
    if not LATENCY_DB_PATH.exists():
        return None
    return db.fetch_one(
        """
        SELECT id, iface, target, count, timeout, enabled, created_at, updated_at
        FROM latency_targets
        WHERE id = ?
        """,
        (target_id,),
        db_path=LATENCY_DB_PATH,
    )


def latency_positive_int(value: Any, default: int) -> int:
    """Return a positive integer from untrusted latency input."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return parsed if parsed > 0 else default


def latency_payload_values(payload: dict[str, Any], current: dict[str, Any] | None = None) -> tuple[str, str, int, int]:
    """Normalize latency target values from request payload."""
    current = current or {}
    iface = str(payload.get("iface") or current.get("iface") or "").strip()
    target = str(payload.get("target") or current.get("target") or "").strip()
    count = latency_positive_int(payload.get("count", current.get("count", 3)), int(current.get("count", 3)))
    timeout = latency_positive_int(payload.get("timeout", current.get("timeout", 3)), int(current.get("timeout", 3)))

    if not iface or not target:
        raise ValueError("Interface and target are required.")

    return iface, target, count, timeout


def create_latency_target(payload: dict[str, Any]) -> dict[str, Any]:
    """Create one configured latency target."""
    iface, target, count, timeout = latency_payload_values(payload)

    try:
        with db.transaction(LATENCY_DB_PATH) as conn:
            cursor = db.execute_on(
                conn,
                """
                INSERT INTO latency_targets (
                    iface, target, count, timeout, enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (iface, target, count, timeout),
            )
            target_id = int(cursor.lastrowid)
    except db.DatabaseError as exc:
        raise ValueError(str(exc)) from exc

    created = latency_target_or_none(target_id)
    if created is None:
        raise ValueError("Latency target not found after create.")
    return latency_target_payload(created)


def update_latency_target(target_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Update one configured latency target."""
    current = latency_target_or_none(target_id)
    if current is None:
        raise ValueError("Latency target not found.")

    iface, target, count, timeout = latency_payload_values(payload, current)

    try:
        db.execute(
            """
            UPDATE latency_targets
            SET iface = ?,
                target = ?,
                count = ?,
                timeout = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (iface, target, count, timeout, target_id),
            db_path=LATENCY_DB_PATH,
        )
    except db.DatabaseError as exc:
        raise ValueError(str(exc)) from exc

    updated = latency_target_or_none(target_id)
    if updated is None:
        raise ValueError("Latency target not found after update.")
    return latency_target_payload(updated)


def set_latency_target_enabled(target_id: int, enabled: bool) -> dict[str, Any]:
    """Enable or disable one configured latency target."""
    if latency_target_or_none(target_id) is None:
        raise ValueError("Latency target not found.")
    db.execute(
        """
        UPDATE latency_targets
        SET enabled = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (1 if enabled else 0, target_id),
        db_path=LATENCY_DB_PATH,
    )
    updated = latency_target_or_none(target_id)
    if updated is None:
        raise ValueError("Latency target not found after status update.")
    return latency_target_payload(updated)


def delete_latency_target(target_id: int) -> None:
    """Delete one configured latency target."""
    affected = db.execute(
        "DELETE FROM latency_targets WHERE id = ?",
        (target_id,),
        db_path=LATENCY_DB_PATH,
    )
    if affected == 0:
        raise ValueError("Latency target not found.")


def latency_graphs_for_target(target: dict[str, str]) -> list[dict[str, str]]:
    """Build graph descriptors for one latency target."""
    safe_name = target["safe_name"]
    label = target["label"]
    graphs: list[dict[str, str]] = []
    for graph_type in LATENCY_GRAPH_TYPES:
        suffix = graph_type["suffix"]
        graphs.append(
            {
                "id": f"latency-{safe_name}-{suffix}",
                "title": f"{label} {graph_type['title']}",
                "description": graph_type["description"],
                "filename": f"latency-{safe_name}-{suffix}.png",
                "rrd": f"latency-{safe_name}.rrd",
                "latency_target_name": safe_name,
                "latency_target_label": label,
            }
        )
    return graphs


def get_latency_graphs() -> dict[str, Any]:
    """Return latency graph metadata for the frontend."""
    graphs: list[dict[str, Any]] = []
    targets = read_configured_latency_targets()
    for target in targets:
        graphs.extend(graph_payload(graph) for graph in latency_graphs_for_target(target))
    return {
        "graphs": graphs,
        "targets": targets,
        "latency_targets": targets,
        "periods": GRAPH_PERIODS,
    }


def render_cpu_mem(request: Request) -> HTMLResponse:
    """Render the CPU and memory monitoring template."""
    return templates.TemplateResponse(
        request,
        "monitoring/cpu_mem.html",
        context=page_context(request, "CPU & Mem") | get_cpu_mem_graphs(),
    )


def render_network(request: Request) -> HTMLResponse:
    """Render the network monitoring template."""
    return templates.TemplateResponse(
        request,
        "monitoring/network.html",
        context=page_context(request, "Network") | get_network_graphs(),
    )


def render_system(request: Request) -> HTMLResponse:
    """Render the system monitoring template."""
    return templates.TemplateResponse(
        request,
        "monitoring/system.html",
        context=page_context(request, "System") | get_system_graphs(),
    )


def render_socket_states(request: Request) -> HTMLResponse:
    """Render the socket states monitoring template."""
    return templates.TemplateResponse(
        request,
        "monitoring/socket_states.html",
        context=page_context(request, "Socket States") | get_socket_state_graphs(),
    )


def render_filesystem(request: Request) -> HTMLResponse:
    """Render the filesystem monitoring template."""
    return templates.TemplateResponse(
        request,
        "monitoring/filesystem.html",
        context=page_context(request, "Filesystem") | get_filesystem_graphs(),
    )


def render_latency(request: Request) -> HTMLResponse:
    """Render the latency monitoring template."""
    return templates.TemplateResponse(
        request,
        "monitoring/latency.html",
        context=page_context(request, "Latency") | get_latency_graphs(),
    )
