from __future__ import annotations

import subprocess
from datetime import datetime
from typing import Any

from core.constants import SUPERVISOR_CONF
from core.process import command_exists, run_command
from core.service_catalog import main_service_public_catalog, optional_service_public_catalog
from web.constants import SERVICES_STATUS_ACTIONS


def supervisor_command(
    *args: str,
    timeout: int = 8,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run supervisorctl against the ArmFirewall supervisor configuration."""
    return run_command(
        ["supervisorctl", "-c", str(SUPERVISOR_CONF), *args],
        timeout=timeout,
        check=check,
    )


def parse_supervisor_status_line(line: str) -> dict[str, str] | None:
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
    """Return supervisor managed program status entries for the Web API."""
    if not SUPERVISOR_CONF.exists() or not command_exists("supervisorctl"):
        return []

    result = supervisor_command("status")
    rows: list[dict[str, str]] = []

    for line in result.stdout.splitlines():
        row = parse_supervisor_status_line(line)
        if row:
            rows.append(row)

    return rows


def supervisor_program_exists(program_name: str) -> bool:
    """Return whether a supervisor program section exists."""
    if not SUPERVISOR_CONF.exists():
        return False

    return f"[program:{program_name}]" in SUPERVISOR_CONF.read_text(encoding="utf-8")


def expected_service_statuses(supervisor_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Merge expected ArmFirewall services with current supervisor state."""
    by_name = {row["name"]: row for row in supervisor_rows}
    services: list[dict[str, Any]] = []

    for service in main_service_public_catalog():
        row = by_name.get(service["name"])
        installed = row is not None

        services.append(
            {
                "name": service["name"],
                "kind": service["kind"],
                "description": service["description"],
                "protected": bool(service["protected"]),
                "restart_allowed": bool(service.get("restart_allowed")),
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
    
    for service in optional_service_public_catalog():
        row = by_name.get(service["name"])
        installed = row is not None

        services.append(
            {
                "name": service["name"],
                "display_name": service["display_name"],
                "kind": service["kind"],
                "description": service["description"],
                "installed": installed,
                "state": row["state"] if row else "NOT INSTALLED",
                "pid": row["pid"] if row else "-",
                "uptime": row["uptime"] if row else "-",
                "details": row["details"] if row else "Missing from supervisord.conf",
                "can_install": not installed,
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


def get_expected_service(name: str) -> dict[str, Any]:
    """Return expected service metadata by name."""
    service = next((item for item in main_service_public_catalog() if item["name"] == name), None)

    if service is None:
        raise ValueError("Unknown ArmFirewall service.")
    
    return service


def get_optional_service(name: str) -> dict[str, Any]:
    """Return optional service metadata by name."""
    service = next((item for item in optional_service_public_catalog() if item["name"] == name), None)

    if service is None:
        raise ValueError("Unknown optional ArmFirewall service.")
    
    return service


def control_service(name: str, action: str) -> dict[str, Any]:
    """Validate service control and return the work request payload."""
    expected_names = {service["name"] for service in main_service_public_catalog()}
    optional_names = {service["name"] for service in optional_service_public_catalog()}

    if name in expected_names:
        service = get_expected_service(name)

        if service["protected"] and not (action == "restart" and service.get("restart_allowed")):
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

    if action not in SERVICES_STATUS_ACTIONS:
        raise ValueError("Unsupported service action.")
    
    return {
        "name": name,
        "action": action,
        "category_name": "SERVICE_MANAGEMENT.SERVICE_CONTROL",
        "payload": payload,
    }


def install_optional_service(name: str) -> dict[str, Any]:
    """Validate optional service installation and return the work request payload."""
    service = get_optional_service(name)

    payload = {
        "service_name": service["name"],
        "display_name": service["display_name"],
    }

    return {
        "name": service["name"],
        "action": "install",
        "category_name": "SERVICE_MANAGEMENT.OPTIONAL_SERVICES",
        "payload": payload,
    }


def uninstall_optional_service(name: str) -> dict[str, Any]:
    """Validate optional service removal and return the work request payload."""
    service = get_optional_service(name)

    payload = {
        "service_name": service["name"],
        "display_name": service["display_name"],
    }

    return {
        "name": service["name"],
        "action": "uninstall",
        "category_name": "SERVICE_MANAGEMENT.OPTIONAL_SERVICES",
        "payload": payload,
    }
