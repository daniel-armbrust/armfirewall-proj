"""Service management actions executed from work requests."""

from __future__ import annotations

import sys

from core import log as logger
from core.constants import CONF_DIR, ROOT_DIR

from .constants import LOG_SOURCE
from .models import ControllableService, OptionalService
from .commons import run_bounded_command
from .packages import install_package, uninstall_package
from .supervisor import (
    register_supervisor_program,
    remove_supervisor_program,
    reread_and_update,
    sync_supervisor_statuses,
    supervisor_command,
    supervisor_program_exists,
    supervisor_status,
)


def validate_api_restart_readiness(state: str) -> None:
    """Validate the web API before allowing a protected restart."""
    if state != "RUNNING":
        raise RuntimeError("armfirewall-api must be RUNNING before a protected restart.")

    cert_path = CONF_DIR / "armfirewall.crt"
    key_path = CONF_DIR / "armfirewall.key"

    if not cert_path.exists():
        raise RuntimeError(f"armfirewall-api TLS certificate was not found: {cert_path}")

    if not key_path.exists():
        raise RuntimeError(f"armfirewall-api TLS key was not found: {key_path}")

    run_bounded_command([sys.executable, "-m", "py_compile", str(ROOT_DIR / "web" / "main.py")], timeout=60)
    run_bounded_command([sys.executable, "-c", "import web.main; assert web.main.app"], timeout=60)


def restart_service(service_name: str) -> None:
    """Restart one supervisord service and verify it returns to RUNNING."""
    supervisor_command("stop", service_name, timeout=60)
    supervisor_command("start", service_name, timeout=60)

    state = supervisor_status(service_name)

    if state != "RUNNING":
        raise RuntimeError(f"Service {service_name} did not return to RUNNING after restart: {state}")


def initialize_libreswan_nss() -> None:
    """Ensure the Libreswan NSS database exists before Pluto is started."""
    run_bounded_command(["ipsec", "checknss"], timeout=60)


def run_post_install_tasks(service: OptionalService) -> None:
    """Run service-specific initialization after package installation."""
    if service.name == "libreswan":
        initialize_libreswan_nss()


def install_service(service: OptionalService) -> None:
    """Install a package and register its supervisor program."""
    install_package(service.package)
    run_post_install_tasks(service)
    register_supervisor_program(service)
    reread_and_update()
    sync_supervisor_statuses()
    logger.log(f"Installed optional service {service.name}.", source=LOG_SOURCE)


def uninstall_service(service: OptionalService) -> None:
    """Stop, unregister, and remove one optional service package."""
    if supervisor_program_exists(service.name):
        supervisor_command("stop", service.name, check=False)
        remove_supervisor_program(service.name)
        reread_and_update()
    
    uninstall_package(service.package)
    sync_supervisor_statuses()
    
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
        if service_name == "armfirewall-api":
            validate_api_restart_readiness(state)
            restart_service(service_name)
        elif state == "RUNNING":
            restart_service(service_name)
        else:
            supervisor_command("start", service_name, timeout=60)
    else:
        raise RuntimeError(f"Unsupported service control action: {action}")

    sync_supervisor_statuses()
    logger.log(f"Service {service_name} {action} completed.", source=LOG_SOURCE)
