"""Structured command-extraction results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class CommandExtraction:
    """Entities extracted from one classified ADAM command."""

    intent: str
    entities: Mapping[str, str | int]

    def to_dict(self) -> dict[str, object]:
        """Return an API-safe command representation."""
        return {
            "intent": self.intent,
            "entities": dict(self.entities),
        }
