"""Shared helpers used by the service management executor."""

from __future__ import annotations

from core.process import run_command


def run_bounded_command(command: list[str], timeout: int = 300, *, check: bool = True):
    """Run a bounded external command."""
    return run_command(command, timeout=timeout, check=check)
