"""Data models used by the service management executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


Payload = dict[str, Any]


@dataclass(frozen=True)
class OptionalService:
    """Optional service package and supervisor metadata."""

    name: str
    package: str
    binary: str
    supervisor_program: str


@dataclass(frozen=True)
class ControllableService:
    """ArmFirewall supervisord service that can be controlled."""

    name: str
