"""Service management actions executed from work requests."""

from __future__ import annotations

from core import log as logger

from .constants import LOG_SOURCE
from .models import ControllableService, OptionalService
from .packages import install_package, uninstall_package
from .supervisor import (
    register_supervisor_program,
    remove_supervisor_program,
    reread_and_update,
    supervisor_command,
    supervisor_program_exists,
    supervisor_status,
)


def install_service(service: OptionalService) -> None:
    """Install a package and register its supervisor program."""
    install_package(service.package)
    register_supervisor_program(service)
    reread_and_update()
    logger.log(f"Installed optional service {service.name}.", source=LOG_SOURCE)


def uninstall_service(service: OptionalService) -> None:
    """Stop, unregister, and remove one optional service package."""
    if supervisor_program_exists(service.name):
        supervisor_command("stop", service.name, check=False)
        remove_supervisor_program(service.name)
        reread_and_update()
    
    uninstall_package(service.package)
    
    logger.log(f"Uninstalled optional service {service.name}.", source=LOG_SOURCE)


def control_service(service: ControllableService, action: str) -> None:
    """Start, stop, or restart one ArmFirewall supervisord service."""
    service_name = service.name
    
    reread_and_update()

    state = supervisor_status(service_name)
    
    if action == "start":
        if state == "RUNNING":
            logger.log(f"Service {service_name} is already running.", source=LOG_SOURCE)
            return
        supervisor_command("start", service_name, timeout=60)
    elif action == "stop":
        if state != "RUNNING":
            logger.log(f"Service {service_name} is already stopped.", source=LOG_SOURCE)
            return
        supervisor_command("stop", service_name, timeout=60)
    elif action == "restart":
        if state == "RUNNING":
            supervisor_command("restart", service_name, timeout=60)
        else:
            supervisor_command("start", service_name, timeout=60)
    else:
        raise RuntimeError(f"Unsupported service control action: {action}")

    logger.log(f"Service {service_name} {action} completed.", source=LOG_SOURCE)
