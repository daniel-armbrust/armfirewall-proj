"""Shared typing models for the ArmFirewall monitoring daemon."""

from __future__ import annotations

from typing import Protocol


class MonitorCollector(Protocol):
    """Describe a monitoring collector invoked by the daemon loop."""

    name: str

    def collect(self) -> None:
        """Run one collection cycle."""
