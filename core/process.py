"""Shared helpers for running external processes."""

from __future__ import annotations

import subprocess


def run_command_stdout(command: list[str], *, timeout: float | None = None) -> str:
    """Run an external command and return its standard output."""
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return completed.stdout
