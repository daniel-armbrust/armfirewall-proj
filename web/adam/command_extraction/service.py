"""Application service for classified ADAM command extraction."""

from __future__ import annotations

from core.constants import (
    ADAM_CHECK_FIREWALL_RULE_INTENT,
    ADAM_CREATE_FIREWALL_BLOCK_RULE_INTENT,
)

from .extractor import extract_firewall_rule_entities
from .schemas import CommandExtraction


class CommandExtractionError(ValueError):
    """Raised when a command cannot be prepared for entity extraction."""


def extract_command(text: str, intent: str) -> CommandExtraction:
    """Extract command entities according to the classified intent."""
    normalized_text = str(text or "").strip()
    normalized_intent = str(intent or "").strip()

    if not normalized_text:
        raise CommandExtractionError("Command text is required.")
    if not normalized_intent:
        raise CommandExtractionError("Classified intent is required.")

    supported_intents = {
        ADAM_CHECK_FIREWALL_RULE_INTENT,
        ADAM_CREATE_FIREWALL_BLOCK_RULE_INTENT,
    }
    if normalized_intent not in supported_intents:
        raise CommandExtractionError(
            f"Entity extraction is not implemented for intent: {normalized_intent}."
        )

    return CommandExtraction(
        intent=normalized_intent,
        entities=extract_firewall_rule_entities(normalized_text),
    )
