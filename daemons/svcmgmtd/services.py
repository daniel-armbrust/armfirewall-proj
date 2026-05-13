"""Service validation helpers for service management work requests."""

from __future__ import annotations

from .constants import ALLOWED_SERVICES, CONTROLLABLE_SERVICES, PROTECTED_SERVICES
from .models import ControllableService, OptionalService, Payload


def validate_service(payload: Payload) -> OptionalService:
    """Return validated metadata for an allowed optional service."""
    service_name = str(payload.get("service_name") or "").strip()
    service = ALLOWED_SERVICES.get(service_name)
    
    if service is None:
        raise RuntimeError(f"Unsupported optional service: {service_name}")

    package = str(payload.get("package") or "").strip()
    
    if package != service["package"]:
        raise RuntimeError(f"Invalid package for {service_name}: {package}")

    return OptionalService(
        name=service_name,
        package=package,
        binary=service["binary"],
        supervisor_program=str(payload.get("supervisor_program") or "").strip(),
    )


def validate_control_service(payload: Payload) -> ControllableService:
    """Return validated metadata for a controllable supervisord service."""
    service_name = str(payload.get("service_name") or "").strip()
    
    if service_name in PROTECTED_SERVICES:
        raise RuntimeError(f"Protected service cannot be controlled: {service_name}")
    
    if service_name not in CONTROLLABLE_SERVICES:
        raise RuntimeError(f"Unsupported controllable service: {service_name}")
    
    return ControllableService(name=service_name)
