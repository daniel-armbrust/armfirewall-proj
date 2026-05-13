from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core import db
from core.process import command_exists


ROOT_DIR = Path(__file__).resolve().parents[2]
SUPERVISOR_CONF = ROOT_DIR / "conf" / "supervisord.conf"
WORK_REQUEST_DB_PATH = ROOT_DIR / "db" / "work-requests.db"
templates = Jinja2Templates(directory=[ROOT_DIR / "web" / "templates", ROOT_DIR / "templates"])

ARMFIREWALL_SERVICES = [
    {
        "name": "armfirewall-api",
        "kind": "web",
        "protected": True,
        "description": "ArmFirewall HTTPS API and web GUI.",
    },
    {
        "name": "armfirewall-ifaced",
        "kind": "daemon",
        "protected": False,
        "description": "Interface inventory and network metrics collector.",
    },
    {
        "name": "armfirewall-monitord",
        "kind": "daemon",
        "protected": False,
        "description": "RRD monitoring collector and graph generator.",
    },
    {
        "name": "armfirewall-workreqd",
        "kind": "daemon",
        "protected": False,
        "description": "Work request executor for operating system changes.",
    },
    {
        "name": "armfirewall-dnsmasq",
        "kind": "service",
        "protected": False,
        "description": "Dnsmasq DNS/DHCP service managed by ArmFirewall.",
    },
    {
        "name": "armfirewall-linkfailover",
        "kind": "daemon",
        "protected": False,
        "description": "Ping-based default route failover daemon.",
    },
]

SERVICE_ACTIONS = {"start", "stop", "restart"}

OPTIONAL_SERVICES = [
    {
        "name": "armfirewall-squid",
        "display_name": "SQUID Proxy",
        "package": "squid",
        "binary": "/usr/sbin/squid",
        "kind": "proxy",
        "description": "Optional Squid proxy service managed by ArmFirewall.",
        "supervisor_program": """
[program:armfirewall-squid]
directory={root}
command=/usr/sbin/squid -N -f /etc/squid/squid.conf
autostart=false
autorestart=true
startsecs=3
stopsignal=TERM
stopasgroup=true
killasgroup=true
stdout_logfile={root}/logs/armfirewall-squid.out.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=5
stderr_logfile={root}/logs/armfirewall-squid.err.log
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=5
""",
    },
]


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for service pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def run_command(command: list[str], timeout: int = 8) -> subprocess.CompletedProcess[str]:
    """Run a bounded command and capture text output."""
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def supervisor_command(*args: str, timeout: int = 8) -> subprocess.CompletedProcess[str]:
    """Run supervisorctl against the ArmFirewall supervisor configuration."""
    return run_command(["supervisorctl", "-c", str(SUPERVISOR_CONF), *args], timeout=timeout)


def parse_supervisor_status_line(line: str) -> Optional[dict[str, str]]:
    """Parse one supervisorctl status line."""
    parts = line.split(None, 2)
    if len(parts) < 2:
        return None
    name = parts[0]
    state = parts[1]
    details = parts[2] if len(parts) > 2 else ""
    pid = "-"
    uptime = "-"
    if "pid " in details:
        after_pid = details.split("pid ", 1)[1]
        pid = after_pid.split(",", 1)[0].strip()
    if "uptime " in details:
        uptime = details.split("uptime ", 1)[1].strip()
    return {
        "name": name,
        "state": state,
        "pid": pid,
        "uptime": uptime,
        "details": details or "-",
    }


def supervisor_programs() -> list[dict[str, str]]:
    """Return supervisor managed program status entries."""
    if not SUPERVISOR_CONF.exists() or not command_exists("supervisorctl"):
        return []
    result = supervisor_command("status")
    rows: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        row = parse_supervisor_status_line(line)
        if row:
            rows.append(row)
    return rows


def package_manager_install_command(package: str) -> Optional[list[str]]:
    """Build an install command for the available package manager."""
    if command_exists("dnf"):
        return ["dnf", "-y", "install", package]
    if command_exists("yum"):
        return ["yum", "-y", "install", package]
    if command_exists("apt-get"):
        return ["apt-get", "-y", "install", package]
    return None


def expected_service_statuses(supervisor_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Merge expected ArmFirewall services with current supervisor state."""
    by_name = {row["name"]: row for row in supervisor_rows}
    services: list[dict[str, Any]] = []
    for service in ARMFIREWALL_SERVICES:
        row = by_name.get(service["name"])
        installed = row is not None
        services.append(
            {
                "name": service["name"],
                "kind": service["kind"],
                "description": service["description"],
                "protected": service["protected"],
                "installed": installed,
                "state": row["state"] if row else "NOT INSTALLED",
                "pid": row["pid"] if row else "-",
                "uptime": row["uptime"] if row else "-",
                "details": row["details"] if row else "Missing from supervisord.conf",
            }
        )
    return services


def optional_service_statuses(supervisor_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Merge optional ArmFirewall services with current supervisor state."""
    by_name = {row["name"]: row for row in supervisor_rows}
    services: list[dict[str, Any]] = []
    for service in OPTIONAL_SERVICES:
        row = by_name.get(service["name"])
        installed = row is not None
        services.append(
            {
                "name": service["name"],
                "display_name": service["display_name"],
                "kind": service["kind"],
                "package": service["package"],
                "description": service["description"],
                "installed": installed,
                "state": row["state"] if row else "NOT INSTALLED",
                "pid": row["pid"] if row else "-",
                "uptime": row["uptime"] if row else "-",
                "details": row["details"] if row else "Missing from supervisord.conf",
                "can_install": not installed and package_manager_install_command(service["package"]) is not None,
            }
        )
    return services


def services_status() -> dict[str, Any]:
    """Return ArmFirewall service status data managed by supervisord."""
    supervisor_rows = supervisor_programs()
    services = expected_service_statuses(supervisor_rows)
    optional_services = optional_service_statuses(supervisor_rows)
    running = sum(1 for service in services if service["state"] == "RUNNING")
    installed = sum(1 for service in services if service["installed"])
    return {
        "summary": {
            "services": len(services),
            "installed": installed,
            "running": running,
            "inactive": len(services) - running,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "services": services,
        "optional_services": optional_services,
    }


def get_service_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent ArmFirewall service management work requests."""
    query = """
        SELECT
            id,
            request_uid,
            status,
            source,
            category_name,
            action_name,
            target_rule_id,
            payload_json,
            error_message,
            created_at,
            updated_at
        FROM work_requests
        WHERE category_name IN (
            'SERVICE_MANAGEMENT.SERVICE_CONTROL',
            'SERVICE_MANAGEMENT.OPTIONAL_SERVICES'
        )
        ORDER BY id DESC
        LIMIT ?
    """
    with db.connection(WORK_REQUEST_DB_PATH) as conn:
        raw_rows = db.fetch_all_on(conn, query, (limit,))

    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        payload = {}
        try:
            payload = json.loads(str(row.get("payload_json") or "{}"))
        except json.JSONDecodeError:
            payload = {}
        item = dict(row)
        item["service_name"] = payload.get("service_name", "-")
        item["display_name"] = payload.get("display_name", item["service_name"])
        item.pop("payload_json", None)
        rows.append(item)

    summary = {"total": len(rows), "queue": 0, "running": 0, "success": 0, "failed": 0}
    for row in rows:
        status = str(row.get("status") or "")
        if status in summary:
            summary[status] += 1

    return {"summary": summary, "requests": rows}


def get_expected_service(name: str) -> dict[str, Any]:
    """Return expected service metadata by name."""
    service = next((item for item in ARMFIREWALL_SERVICES if item["name"] == name), None)
    if service is None:
        raise ValueError("Unknown ArmFirewall service.")
    return service


def get_optional_service(name: str) -> dict[str, Any]:
    """Return optional service metadata by name."""
    service = next((item for item in OPTIONAL_SERVICES if item["name"] == name), None)
    if service is None:
        raise ValueError("Unknown optional ArmFirewall service.")
    return service


def control_service(name: str, action: str) -> dict[str, Any]:
    """Queue start, stop, or restart for one non-protected ArmFirewall service."""
    expected_names = {service["name"] for service in ARMFIREWALL_SERVICES}
    optional_names = {service["name"] for service in OPTIONAL_SERVICES}
    if name in expected_names:
        service = get_expected_service(name)
        if service["protected"]:
            raise ValueError("Protected services cannot be controlled from the GUI.")
        payload = {
            "service_name": service["name"],
            "display_name": service["name"],
            "kind": service["kind"],
        }
    elif name not in optional_names:
        raise ValueError("Unknown ArmFirewall service.")
    else:
        service = get_optional_service(name)
        payload = {
            "service_name": service["name"],
            "display_name": service["display_name"],
            "kind": service["kind"],
        }
    if action not in SERVICE_ACTIONS:
        raise ValueError("Unsupported service action.")
    work_request_id = queue_service_work_request(action, payload, category_name="SERVICE_MANAGEMENT.SERVICE_CONTROL")
    return {
        "name": name,
        "action": action,
        "status": "queue",
        "work_request_id": work_request_id,
    }


def install_optional_service(name: str) -> dict[str, Any]:
    """Queue installation for one optional ArmFirewall service."""
    service = get_optional_service(name)
    payload = {
        "service_name": service["name"],
        "display_name": service["display_name"],
        "package": service["package"],
        "binary": service["binary"],
        "supervisor_program": service["supervisor_program"],
    }
    work_request_id = queue_service_work_request("install", payload)
    return {
        "name": service["name"],
        "package": service["package"],
        "status": "queue",
        "work_request_id": work_request_id,
    }


def uninstall_optional_service(name: str) -> dict[str, Any]:
    """Queue uninstallation for one optional ArmFirewall service."""
    service = get_optional_service(name)
    payload = {
        "service_name": service["name"],
        "display_name": service["display_name"],
        "package": service["package"],
        "binary": service["binary"],
    }
    work_request_id = queue_service_work_request("uninstall", payload)
    return {
        "name": service["name"],
        "package": service["package"],
        "status": "queue",
        "work_request_id": work_request_id,
    }


def queue_service_work_request(
    action: str,
    payload: dict[str, Any],
    *,
    category_name: str = "SERVICE_MANAGEMENT.OPTIONAL_SERVICES",
) -> int:
    """Insert a service management work request and return its id."""
    if action not in {"install", "uninstall", "start", "stop", "restart"}:
        raise ValueError("Unsupported service management action.")
    if category_name not in {"SERVICE_MANAGEMENT.OPTIONAL_SERVICES", "SERVICE_MANAGEMENT.SERVICE_CONTROL"}:
        raise ValueError("Unsupported service management category.")
    request_uid = str(uuid.uuid4())
    with db.transaction(WORK_REQUEST_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (
                request_uid, source, category_name, action_name,
                target_rule_id, priority, status, payload_json
            )
            VALUES (?, 'gui', ?, ?, NULL, 80, 'queue', ?)
            """,
            (request_uid, category_name, action, json.dumps(payload, sort_keys=True)),
        )
        work_request_id = int(cursor.lastrowid)
        db.execute_on(
            conn,
            """
            INSERT INTO work_request_events (work_request_id, event_type, message)
            VALUES (?, 'queue', ?)
            """,
            (work_request_id, f"Queued service {action}: {payload.get('service_name')}"),
        )
        return work_request_id


def render_status(request: Request) -> HTMLResponse:
    """Render the Services / Status page."""
    return templates.TemplateResponse(
        request,
        "services/status.html",
        context=page_context(request, "Status"),
    )
