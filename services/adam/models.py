"""Data models shared by ADAM application services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IntentPrediction:
    """One normalized classifier prediction."""

    label: str
    confidence: float
    model_id: str


@dataclass(frozen=True)
class PendingAction:
    """One user-bound destructive action awaiting confirmation."""

    actor: str
    intent: str
    parameters: dict[str, Any]
    expires_at: float
