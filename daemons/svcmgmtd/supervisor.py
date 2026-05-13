"""Supervisor operations for ArmFirewall managed services."""

from __future__ import annotations

from core.constants import ROOT_DIR
from core.process import command_exists

from .commons import run_bounded_command
from .constants import SUPERVISOR_CONF
from .models import OptionalService


def supervisor_program_exists(program_name: str) -> bool:
    """Return whether a supervisor program section exists."""
    if not SUPERVISOR_CONF.exists():
        return False

    return f"[program:{program_name}]" in SUPERVISOR_CONF.read_text(encoding="utf-8")


def supervisor_command(*args: str, timeout: int = 60, check: bool = True):
    """Run supervisorctl against the ArmFirewall supervisor configuration."""
    if not command_exists("supervisorctl"):
        raise RuntimeError("supervisorctl was not found.")
    
    return run_bounded_command(["supervisorctl", "-c", str(SUPERVISOR_CONF), *args], timeout=timeout, check=check)


def supervisor_status(service_name: str) -> str:
    """Return a supervisord program state, tolerating stopped return codes."""
    result = supervisor_command("status", service_name, check=False)
    output = (result.stdout + result.stderr).strip()
    
    if "no such process" in output.lower():
        raise RuntimeError(f"Supervisor program is not registered: {service_name}")
    
    states = {"RUNNING", "STOPPED", "STARTING", "BACKOFF", "STOPPING", "EXITED", "FATAL", "UNKNOWN"}
    state = next((item for item in states if item in output), "")
    
    if not state:
        raise RuntimeError(output or f"Could not read supervisor status for {service_name}.")
    
    return state


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


def reread_and_update() -> None:
    """Refresh supervisord program definitions."""
    supervisor_command("reread", check=False)
    supervisor_command("update", check=False)
