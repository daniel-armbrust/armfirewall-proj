"""Shared template context helpers for the ArmFirewall Web layer."""

from __future__ import annotations

from typing import Any

from core import db
from core.constants import (
    ADAM_LISTENING_STORAGE_KEY,
    ADAM_WAKE_WORD,
    ADAM_WAKE_WORD_ENGINE_URL,
    ADAM_WAKE_WORD_MIN_CONFIDENCE,
    ADAM_WAKE_WORD_MODEL_URL,
    ADAM_WAKE_WORD_WORKLET_URL,
)
from web.services.api import service_installed


def menu_context() -> dict[str, Any]:
    """Return dynamic menu state for template rendering."""
    try:
        squid_installed = service_installed("squid")
    except (FileNotFoundError, db.DatabaseError):
        squid_installed = False

    try:
        libreswan_installed = service_installed("libreswan")
    except (FileNotFoundError, db.DatabaseError):
        libreswan_installed = False

    return {
        "squid_installed": squid_installed,
        "libreswan_installed": libreswan_installed,
        "adam_listening_storage_key": ADAM_LISTENING_STORAGE_KEY,
        "adam_wake_word": ADAM_WAKE_WORD,
        "adam_wake_word_engine_url": ADAM_WAKE_WORD_ENGINE_URL,
        "adam_wake_word_min_confidence": ADAM_WAKE_WORD_MIN_CONFIDENCE,
        "adam_wake_word_model_url": ADAM_WAKE_WORD_MODEL_URL,
        "adam_wake_word_worklet_url": ADAM_WAKE_WORD_WORKLET_URL,
    }
