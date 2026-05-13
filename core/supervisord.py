"""Shared supervisord helpers for ArmFirewall."""

from __future__ import annotations

import subprocess

from core.constants import SUPERVISOR_CONF
from core.process import command_exists, run_command


SUPERVISOR_STATES = {"RUNNING", "STOPPED", "STARTING", "BACKOFF", "STOPPING", "EXITED", "FATAL", "UNKNOWN"}


def supervisor_command(
    *args: str,
    timeout: int = 60,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run supervisorctl against the ArmFirewall supervisor configuration."""
    if not command_exists("supervisorctl"):
        raise RuntimeError("supervisorctl was not found.")

    return run_command(["supervisorctl", "-c", str(SUPERVISOR_CONF), *args], timeout=timeout, check=check)


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
    """Return supervisor managed program status entries."""
    if not SUPERVISOR_CONF.exists() or not command_exists("supervisorctl"):
        return []

    result = supervisor_command("status", check=False)
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


def supervisor_status(service_name: str) -> str:
    """Return a supervisord program state, tolerating stopped return codes."""
    result = supervisor_command("status", service_name, check=False)
    output = (result.stdout + result.stderr).strip()

    if "no such process" in output.lower():
        raise RuntimeError(f"Supervisor program is not registered: {service_name}")

    state = next((item for item in SUPERVISOR_STATES if item in output), "")

    if not state:
        raise RuntimeError(output or f"Could not read supervisor status for {service_name}.")

    return state
