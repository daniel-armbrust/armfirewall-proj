"""Service management actions executed from work requests."""

from __future__ import annotations

import sys

from core import db
from core import log as logger
from core.constants import (
    ADGUARD_HOME_SERVICE_NAME,
    CONF_DIR,
    DNSMASQ_LEASES_PATH,
    ROOT_DIR,
    SERVICES_DB_PATH,
)

from .constants import LOG_SOURCE
from .catalog import set_service_autostart_enabled
from .models import ControllableService, OptionalService
from .commons import run_bounded_command
from .packages import (
    configure_adguard_home_dns_listener,
    install_adguard_home,
    install_package,
    uninstall_adguard_home,
    uninstall_package,
)
from daemons.dnsmasq.dns_routing import ensure_lan_dns_input_rules
from daemons.dnsmasq.dnsmasq import apply_config as apply_dnsmasq_config
from .supervisor import (
    register_supervisor_program,
    remove_supervisor_program,
    reread_and_update,
    set_supervisor_program_autostart,
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


def ensure_dnsmasq_lease_directory(service_name: str) -> None:
    """Create the runtime directory required by Dnsmasq before it starts."""
    if service_name == "dnsmasq":
        DNSMASQ_LEASES_PATH.parent.mkdir(parents=True, exist_ok=True)


def install_service(service: OptionalService) -> None:
    """Install a package with autostart disabled until the user enables it."""
    if service.name == ADGUARD_HOME_SERVICE_NAME:
        install_adguard_home()
        configure_adguard_home_dns_listener()
        ensure_lan_dns_input_rules()
    else:
        install_package(service.package)
    register_supervisor_program(service)
    set_supervisor_program_autostart(service.name, False)
    set_service_autostart_enabled(service.name, False)
    reread_and_update()
    sync_supervisor_statuses()
    logger.log(f"Installed optional service {service.name}.", source=LOG_SOURCE)


def uninstall_service(service: OptionalService) -> None:
    """Stop, unregister, and remove one optional service package."""
    if supervisor_program_exists(service.name):
        supervisor_command("stop", service.name, check=False)
        remove_supervisor_program(service.name)
        reread_and_update()
    
    if service.name == ADGUARD_HOME_SERVICE_NAME:
        uninstall_adguard_home()
    else:
        uninstall_package(service.package)
    set_service_autostart_enabled(service.name, False)
    sync_supervisor_statuses()
    
    logger.log(f"Uninstalled optional service {service.name}.", source=LOG_SOURCE)


def control_service(service: ControllableService, action: str) -> None:
    """Apply one allowed runtime or enablement action to a managed service."""
    service_name = service.name

    ensure_dnsmasq_lease_directory(service_name)
    if service_name == ADGUARD_HOME_SERVICE_NAME and action in {"start", "restart"}:
        configure_adguard_home_dns_listener()
        ensure_lan_dns_input_rules()
    reread_and_update()

    if service_name == ADGUARD_HOME_SERVICE_NAME and action in {"start", "restart"}:
        apply_dnsmasq_config(adguard_active=True)
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
    elif action == "enable":
        set_supervisor_program_autostart(service_name, True)
        set_service_autostart_enabled(service_name, True)
    elif action == "disable":
        if state == "RUNNING":
            supervisor_command("stop", service_name, timeout=60)
        set_supervisor_program_autostart(service_name, False)
        set_service_autostart_enabled(service_name, False)
    else:
        raise RuntimeError(f"Unsupported service control action: {action}")

    if action in {"enable", "disable"}:
        reread_and_update()
    if service_name == ADGUARD_HOME_SERVICE_NAME and action in {"stop", "disable"}:
        apply_dnsmasq_config(adguard_active=False)
    sync_supervisor_statuses()
    logger.log(f"Service {service_name} {action} completed.", source=LOG_SOURCE)


def set_feature_enabled(service_name: str, enabled: bool) -> None:
    """Persist visibility of a GUI-managed feature service."""
    with db.transaction(SERVICES_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            "UPDATE services SET enabled = ? WHERE name = ?",
            (1 if enabled else 0, service_name),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(f"Feature service was not found: {service_name}")

    logger.log(
        f"Feature service {service_name} {'enabled' if enabled else 'disabled'}.",
        source=LOG_SOURCE,
    )
