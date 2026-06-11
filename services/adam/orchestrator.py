"""Orchestrate ADAM intent classification and approved application actions."""

from __future__ import annotations

import re
import secrets
import threading
import time
from typing import Any

from daemons.fwrulesd.filter import rules as filter_core
from daemons.workreqd.queue import queue_work_request

from .inference import IntentClassifier, ModelUnavailableError
from .models import PendingAction


MINIMUM_ACTION_CONFIDENCE = 0.70
CONFIRMATION_TTL_SECONDS = 300
MUTATING_ROLES = {"admin", "operator"}
SUPPORTED_ACTION_INTENTS = {"delete_firewall_rule"}
FILTER_CHAIN_TABLES = {
    "INPUT": "filter_input_rules",
    "FORWARD": "filter_forward_rules",
    "OUTPUT": "filter_output_rules",
}


class OrchestrationError(RuntimeError):
    """Represent an expected ADAM command processing failure."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ConfirmationStore:
    """Keep short-lived, one-time confirmation tokens in the API process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, PendingAction] = {}

    def create(self, *, actor: str, intent: str, parameters: dict[str, Any]) -> str:
        """Create a user-bound confirmation token."""
        token = secrets.token_urlsafe(32)
        now = time.monotonic()
        with self._lock:
            self._items = {
                key: item
                for key, item in self._items.items()
                if item.expires_at > now
            }
            self._items[token] = PendingAction(
                actor=actor,
                intent=intent,
                parameters=dict(parameters),
                expires_at=now + CONFIRMATION_TTL_SECONDS,
            )
        return token

    def consume(self, token: str, *, actor: str) -> PendingAction:
        """Consume a valid token exactly once for the same authenticated user."""
        now = time.monotonic()
        with self._lock:
            item = self._items.pop(token, None)
        if item is None or item.expires_at <= now:
            raise OrchestrationError(
                "The confirmation token is invalid or expired.",
                409,
            )
        if item.actor != actor:
            raise OrchestrationError(
                "The confirmation token belongs to another user.",
                403,
            )
        return item


def _normalize_parameters(text: str, supplied: dict[str, Any]) -> dict[str, Any]:
    """Normalize structured parameters and extract only unambiguous text values."""
    parameters: dict[str, Any] = {}

    family_value = str(supplied.get("family") or "").upper().replace(" ", "")
    family_match = re.search(r"\bIPV\s*([46])\b", text, re.IGNORECASE)
    if family_value in {"IPV4", "IPV6"}:
        parameters["family"] = family_value
    elif family_match:
        parameters["family"] = f"IPV{family_match.group(1)}"

    chain_value = str(supplied.get("chain") or "").upper()
    chain_match = re.search(r"\b(INPUT|FORWARD|OUTPUT)\b", text, re.IGNORECASE)
    if chain_value in {"INPUT", "FORWARD", "OUTPUT"}:
        parameters["chain"] = chain_value
    elif chain_match:
        parameters["chain"] = chain_match.group(1).upper()

    rule_id_value = supplied.get("rule_id")
    if isinstance(rule_id_value, int) and not isinstance(rule_id_value, bool):
        rule_id = rule_id_value
    elif isinstance(rule_id_value, str) and rule_id_value.isdigit():
        rule_id = int(rule_id_value)
    else:
        rule_match = re.search(
            r"\b(?:regra|rule)\s*(?:de\s+)?(?:id|#|n[uú]mero)\s*[:#-]?\s*(\d+)\b",
            text,
            re.IGNORECASE,
        )
        rule_id = int(rule_match.group(1)) if rule_match else 0
    if rule_id > 0:
        parameters["rule_id"] = rule_id

    return parameters


def _get_filter_rule(family: str, chain: str, rule_id: int) -> dict[str, Any]:
    """Read one filter rule for confirmation without changing firewall state."""
    try:
        return filter_core.get_filter_rule(family, chain, rule_id)
    except filter_core.FilterRuleError as exc:
        raise OrchestrationError(str(exc), exc.status_code) from exc


def _queue_filter_rule_removal(
    *,
    family: str,
    chain: str,
    rule_id: int,
    requested_by: str,
) -> dict[str, Any]:
    """Queue a removal for exclusive execution by fwrulesd."""
    normalized_family = family.upper()
    normalized_chain = chain.upper()
    table = FILTER_CHAIN_TABLES.get(normalized_chain)
    if normalized_family not in {"IPV4", "IPV6"} or table is None or rule_id <= 0:
        raise OrchestrationError("Invalid firewall rule removal parameters.")

    rule = _get_filter_rule(normalized_family, normalized_chain, rule_id)
    if int(rule.get("protected") or 0) == 1:
        raise OrchestrationError("Protected filter rules cannot be deleted.", 403)
    if int(rule.get("enabled") or 0) == 0:
        raise OrchestrationError("Disabled filter rules cannot be deleted.", 403)

    category_name = f"FIREWALL_RULES.{normalized_family}.{table}"
    payload = {
        "family": normalized_family,
        "chain": normalized_chain,
        "table": table,
        "rule_id": rule_id,
        "delete_from_database": True,
        "requested_by": requested_by,
        "requested_via": "adam",
    }
    try:
        queued = queue_work_request(
            action="remove",
            payload=payload,
            category_name=category_name,
            source="api",
            target_rule_id=rule_id,
            allowed_actions=("remove",),
            allowed_categories=(category_name,),
            event_message=(
                f"ADAM queued removal of {normalized_family} {normalized_chain} "
                f"filter rule {rule_id} for user {requested_by}."
            ),
        )
    except (OSError, ValueError) as exc:
        raise OrchestrationError(
            "The firewall rule removal work request could not be created.",
            500,
        ) from exc
    return {
        "requested_by": requested_by,
        "family": normalized_family,
        "chain": normalized_chain,
        "rule_id": rule_id,
        **queued,
    }


class AdamOrchestrator:
    """Coordinate classification, clarification, confirmation and execution."""

    def __init__(
        self,
        classifier: IntentClassifier | None = None,
        confirmations: ConfirmationStore | None = None,
    ) -> None:
        self._classifier = classifier or IntentClassifier()
        self._confirmations = confirmations or ConfirmationStore()

    @staticmethod
    def _actor(user: dict[str, Any]) -> tuple[str, str]:
        username = str(user.get("username") or "").strip()
        role = str(user.get("role") or "").strip().lower()
        if not username:
            raise OrchestrationError("Authentication is required.", 401)
        return username, role

    def _execute(self, pending: PendingAction) -> dict[str, Any]:
        if pending.intent != "delete_firewall_rule":
            raise OrchestrationError("The confirmed action is not supported.", 400)
        result = _queue_filter_rule_removal(
            family=str(pending.parameters["family"]),
            chain=str(pending.parameters["chain"]),
            rule_id=int(pending.parameters["rule_id"]),
            requested_by=pending.actor,
        )
        return {
            "status": "queued",
            "intent": pending.intent,
            "parameters": pending.parameters,
            "message": "The firewall rule removal was queued successfully.",
            "execution": result,
        }

    def process(
        self,
        *,
        text: str,
        user: dict[str, Any],
        parameters: dict[str, Any] | None = None,
        confirmed: bool = False,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        """Process one user command without allowing implicit mutations."""
        actor, role = self._actor(user)

        if confirmed:
            if role not in MUTATING_ROLES:
                raise OrchestrationError(
                    "Your role is not allowed to change firewall rules.",
                    403,
                )
            if not confirmation_token:
                raise OrchestrationError("A confirmation token is required.", 400)
            pending = self._confirmations.consume(confirmation_token, actor=actor)
            return self._execute(pending)

        try:
            prediction = self._classifier.predict(text)
        except ModelUnavailableError as exc:
            raise OrchestrationError(str(exc), 503) from exc
        except ValueError as exc:
            raise OrchestrationError(str(exc), 400) from exc

        classification = {
            "intent": prediction.label,
            "confidence": prediction.confidence,
            "model_id": prediction.model_id,
        }
        if prediction.confidence < MINIMUM_ACTION_CONFIDENCE:
            return {
                "status": "clarification_required",
                "classification": classification,
                "message": "I could not identify the requested action with enough confidence.",
            }
        if prediction.label not in SUPPORTED_ACTION_INTENTS:
            return {
                "status": "not_supported",
                "classification": classification,
                "message": "The intent was identified, but no action handler is available yet.",
            }
        if role not in MUTATING_ROLES:
            raise OrchestrationError(
                "Your role is not allowed to change firewall rules.",
                403,
            )

        normalized = _normalize_parameters(text, parameters or {})
        missing = [
            name for name in ("family", "chain", "rule_id") if name not in normalized
        ]
        if missing:
            return {
                "status": "clarification_required",
                "classification": classification,
                "parameters": normalized,
                "missing_parameters": missing,
                "message": "Additional firewall rule details are required.",
            }

        rule = _get_filter_rule(
            str(normalized["family"]),
            str(normalized["chain"]),
            int(normalized["rule_id"]),
        )
        if int(rule.get("protected") or 0) == 1:
            raise OrchestrationError("Protected filter rules cannot be deleted.", 403)

        token = self._confirmations.create(
            actor=actor,
            intent=prediction.label,
            parameters=normalized,
        )
        return {
            "status": "confirmation_required",
            "classification": classification,
            "parameters": normalized,
            "confirmation_token": token,
            "confirmation_expires_in_seconds": CONFIRMATION_TTL_SECONDS,
            "message": "Confirm the removal of this firewall rule.",
            "rule": rule,
        }


orchestrator = AdamOrchestrator()
