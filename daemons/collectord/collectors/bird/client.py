"""BIRD command execution helpers."""

from __future__ import annotations

import time
from pathlib import Path

from core.process import command_exists, run_command
from core.supervisord import supervisor_program_exists, supervisor_status

from core.constants import COLLECTORD_BIRD_COMMAND_TIMEOUT_SECONDS, COLLECTORD_BIRDCL_PATH


def run_bird_command(command: list[str]):
    """Run one birdcl command and return the result plus duration."""
    started = time.monotonic()
    completed = run_command(command, check=False, timeout=COLLECTORD_BIRD_COMMAND_TIMEOUT_SECONDS)
    return completed, int((time.monotonic() - started) * 1000)


def bird_is_available() -> bool:
    """Return whether BIRD diagnostics can run on this appliance."""
    if Path(COLLECTORD_BIRDCL_PATH).is_absolute():
        if not Path(COLLECTORD_BIRDCL_PATH).is_file():
            return False
    elif not command_exists(COLLECTORD_BIRDCL_PATH):
        return False

    if not supervisor_program_exists("bird"):
        return False

    try:
        return supervisor_status("bird") == "RUNNING"
    except RuntimeError:
        return False
