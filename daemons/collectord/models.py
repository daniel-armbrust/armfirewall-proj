"""Shared typing models for the ArmFirewall collection daemon."""

from __future__ import annotations

from typing import Protocol


class Collector(Protocol):
    """Describe one collectord collector invoked by the scheduler loop."""

    name: str
    interval_seconds: int

    def collect(self) -> None:
        """Run one collection cycle."""
