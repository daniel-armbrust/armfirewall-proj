"""Service validation helpers for service management work requests."""

from __future__ import annotations

from .catalog import optional_service_for_daemon, service_exists
from .constants import PROTECTED_SERVICES, RESTARTABLE_PROTECTED_SERVICES
from .models import ControllableService, OptionalService, Payload


def validate_service(payload: Payload) -> OptionalService:
    """Return validated metadata for an allowed optional service."""
    service_name = str(payload.get("service_name") or "").strip()
    service = optional_service_for_daemon(service_name)
    
    if service is None:
        raise RuntimeError(f"Unsupported optional service: {service_name}")

    return OptionalService(
        name=service_name,
        package=str(service["package"]),
        binary=str(service["binary"]),
        supervisor_program=str(service["supervisor_program"]),
    )


def validate_control_service(payload: Payload, action: str) -> ControllableService:
    """Return validated metadata for a controllable supervisord service."""
    service_name = str(payload.get("service_name") or "").strip()
    
    if service_name in PROTECTED_SERVICES and not (action == "restart" and service_name in RESTARTABLE_PROTECTED_SERVICES):
        raise RuntimeError(f"Protected service cannot be controlled: {service_name}")
    
    if not service_exists(service_name):
        raise RuntimeError(f"Unsupported controllable service: {service_name}")
    
    return ControllableService(name=service_name)


def validate_feature_toggle(payload: Payload) -> str:
    """Return the only GUI-managed feature service that can be toggled."""
    service_name = str(payload.get("service_name") or "").strip()
    if service_name != "armfirewall-adam":
        raise RuntimeError(f"Unsupported feature service: {service_name}")
    return service_name
