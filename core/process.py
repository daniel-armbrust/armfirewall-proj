"""Shared helpers for running external processes."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class ProcessExecutionError(subprocess.CalledProcessError):
    """CalledProcessError with stderr/stdout included in the string message."""

    def __str__(self) -> str:
        """Return a command-focused failure message."""
        rendered = " ".join(str(part) for part in self.cmd)
        message = (self.stderr or self.output or "command failed").strip()
        return f"{rendered}: {message}"


def command_exists(command: str) -> bool:
    """Return whether one command exists in PATH."""
    return shutil.which(command) is not None


def count_processes() -> int:
    """Count numeric process directories from /proc."""
    proc = Path("/proc")

    if not proc.exists():
        return 0

    return sum(1 for item in proc.iterdir() if item.name.isdigit())


def run_command(
    command: list[str],
    *,
    timeout: float | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run an external command and raise a useful error on failure."""
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        raise ProcessExecutionError(
            completed.returncode,
            command,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed


def run_command_stdout(command: list[str], *, timeout: float | None = None) -> str:
    """Run an external command and return its standard output."""
    completed = run_command(command, timeout=timeout)
    return completed.stdout
