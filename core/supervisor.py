"""Shared helpers for ArmFirewall supervisord configuration."""

from __future__ import annotations

from core.constants import SUPERVISOR_CONF


def supervisor_program_exists(program_name: str) -> bool:
    """Return whether a supervisor program section exists."""
    if not SUPERVISOR_CONF.exists():
        return False
    
    return f"[program:{program_name}]" in SUPERVISOR_CONF.read_text(encoding="utf-8")
