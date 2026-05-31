"""Supervisor operations for ArmFirewall managed services."""

from __future__ import annotations

from core.constants import ROOT_DIR
from core.supervisord import (
    supervisor_command,
    supervisor_program_exists,
    supervisor_programs,
    supervisor_status,
)

from .catalog import persist_supervisor_statuses
from .constants import SUPERVISOR_CONF
from .models import OptionalService


def register_supervisor_program(service: OptionalService) -> None:
    """Append the optional service supervisor program when missing."""
    if not SUPERVISOR_CONF.exists():
        raise RuntimeError(f"ArmFirewall supervisord.conf was not found: {SUPERVISOR_CONF}")
    
    if supervisor_program_exists(service.name):
        return
    
    program = service.supervisor_program.strip()
    
    if not program.startswith(f"[program:{service.name}]"):
        raise RuntimeError(f"Invalid supervisor program payload for {service.name}.")
    
    with SUPERVISOR_CONF.open("a", encoding="utf-8") as handle:
        handle.write("\n")
        handle.write(program.format(root=ROOT_DIR))
        handle.write("\n")


def remove_supervisor_program(service_name: str) -> None:
    """Remove one optional service supervisor program section."""
    if not SUPERVISOR_CONF.exists():
        raise RuntimeError(f"ArmFirewall supervisord.conf was not found: {SUPERVISOR_CONF}")
    
    lines = SUPERVISOR_CONF.read_text(encoding="utf-8").splitlines()
    section = f"[program:{service_name}]"
    output: list[str] = []
    skip = False
    removed = False
    
    for line in lines:
        if line.strip() == section:
            skip = True
            removed = True
            continue
        
        if skip and line.startswith("[") and line.endswith("]"):
            skip = False
        
        if not skip:
            output.append(line)
    
    if removed:
        SUPERVISOR_CONF.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def set_supervisor_program_autostart(service_name: str, enabled: bool) -> None:
    """Persist the autostart setting for one registered supervisor program."""
    if not SUPERVISOR_CONF.exists():
        raise RuntimeError(f"ArmFirewall supervisord.conf was not found: {SUPERVISOR_CONF}")

    lines = SUPERVISOR_CONF.read_text(encoding="utf-8").splitlines()
    section = f"[program:{service_name}]"
    target_value = f"autostart={'true' if enabled else 'false'}"
    output: list[str] = []
    in_section = False
    section_found = False
    autostart_found = False

    for line in lines:
        if line.strip() == section:
            in_section = True
            section_found = True
            autostart_found = False
            output.append(line)
            continue

        if in_section and line.startswith("[") and line.endswith("]"):
            if not autostart_found:
                output.append(target_value)
            in_section = False

        if in_section and line.strip().startswith("autostart="):
            output.append(target_value)
            autostart_found = True
            continue

        output.append(line)

    if in_section and not autostart_found:
        output.append(target_value)

    if not section_found:
        raise RuntimeError(f"Supervisor program is not registered: {service_name}")

    SUPERVISOR_CONF.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def reread_and_update() -> None:
    """Refresh supervisord program definitions."""
    supervisor_command("reread", check=False)
    supervisor_command("update", check=False)
    sync_supervisor_statuses()


def sync_supervisor_statuses() -> None:
    """Persist current supervisord statuses into services.db."""
    persist_supervisor_statuses(supervisor_programs())
