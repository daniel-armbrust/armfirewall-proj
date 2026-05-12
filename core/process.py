"""Shared helpers for running external processes."""

from __future__ import annotations

import subprocess


def run_command(command: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    """Run an external command and raise a useful error on failure."""
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def run_command_stdout(command: list[str], *, timeout: float | None = None) -> str:
    """Run an external command and return its standard output."""
    completed = run_command(command, timeout=timeout)
    return completed.stdout
