from __future__ import annotations

from datetime import datetime
from typing import Any

from core import ipsec
from web.constants import SERVICES_STATUS_ACTIONS
from web.services.catalog import main_service_public_catalog, optional_service_public_catalog, service_by_name


def libreswan_runtime_overlay(payload: dict[str, Any]) -> dict[str, Any]:
    """Reflect active IPsec SAs in the Libreswan service status."""
    if payload["name"] != "libreswan" or not payload["installed"]:
        return payload

    established_names = sorted(ipsec.established_connection_names())
    if not established_names:
        return payload

    updated = dict(payload)
    updated["state"] = "RUNNING"
    updated["details"] = f"IPsec up: {', '.join(established_names)}"
    return updated


def service_status_payload(service: dict[str, Any], *, optional: bool = False) -> dict[str, Any]:
    """Return one service status payload from persisted runtime fields."""
    installed = bool(service.get("runtime_installed"))

    payload = {
        "name": service["name"],
        "kind": service["kind"],
        "description": service["description"],
        "installed": installed,
        "state": service.get("runtime_state") if installed else "NOT INSTALLED",
        "pid": service.get("runtime_pid") if installed else "-",
        "uptime": service.get("runtime_uptime") if installed else "-",
        "details": service.get("runtime_details") if installed else "Missing from supervisord.conf",
        "runtime_updated_at": service.get("runtime_updated_at"),
    }

    if optional:
        payload["display_name"] = service["display_name"]
        payload["can_install"] = not installed
    else:
        payload["protected"] = bool(service["protected"])
        payload["restart_allowed"] = bool(service.get("restart_allowed"))

    return libreswan_runtime_overlay(payload)


def expected_service_statuses() -> list[dict[str, Any]]:
    """Return main ArmFirewall services using persisted runtime state."""
    services: list[dict[str, Any]] = []

    for service in main_service_public_catalog():
        services.append(service_status_payload(service))

    return services


def optional_service_statuses() -> list[dict[str, Any]]:
    """Return optional ArmFirewall services using persisted runtime state."""
    services: list[dict[str, Any]] = []
    
    for service in optional_service_public_catalog():
        services.append(service_status_payload(service, optional=True))

    return services


def services_status() -> dict[str, Any]:
    """Return persisted ArmFirewall service status data."""
    services = expected_service_statuses()
    optional_services = optional_service_statuses()
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


def service_status_by_name(name: str) -> dict[str, Any]:
    """Return one persisted service status by name."""
    service = service_by_name(name)
    if service is None:
        raise ValueError("Unknown ArmFirewall service.")

    return service_status_payload(service, optional=service.get("service_group") == "optional")


def service_installed(name: str) -> bool:
    """Return whether one service is installed according to persisted runtime state."""
    service = service_by_name(name)
    return bool(service and service.get("runtime_installed"))


def get_expected_service(name: str) -> dict[str, Any]:
    """Return expected service metadata by name."""
    service = service_by_name(name)

    if service is None or service.get("service_group") != "main":
        raise ValueError("Unknown ArmFirewall service.")
    
    return service


def get_optional_service(name: str) -> dict[str, Any]:
    """Return optional service metadata by name."""
    service = service_by_name(name)

    if service is None or service.get("service_group") != "optional":
        raise ValueError("Unknown optional ArmFirewall service.")
    
    return service


def control_service(name: str, action: str) -> dict[str, Any]:
    """Validate service control and return the work request payload."""
    service = service_by_name(name)

    if service is None:
        raise ValueError("Unknown ArmFirewall service.")

    if service.get("service_group") == "main":
        if service["protected"] and not (action == "restart" and service.get("restart_allowed")):
            raise ValueError("Protected services cannot be controlled from the GUI.")
        
        payload = {
            "service_name": service["name"],
            "display_name": service["name"],
            "kind": service["kind"],
        }
    else:
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
