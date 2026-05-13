from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any

from core import db
from core.constants import WORK_REQUEST_DB_PATH
from core.workrequest import list_work_requests


SERVICE_WORK_REQUEST_ACTIONS = {"install", "uninstall", "start", "stop", "restart"}
SERVICE_WORK_REQUEST_CATEGORIES = {"SERVICE_MANAGEMENT.OPTIONAL_SERVICES", "SERVICE_MANAGEMENT.SERVICE_CONTROL"}


def get_work_requests(
    *,
    limit: int = 50,
    categories: Sequence[str] | None = None,
    category_like: str | None = None,
    service_name: str | None = None,
    include_payload: bool = False,
) -> dict[str, Any]:
    """Return ArmFirewall work requests for Web API consumers."""
    return list_work_requests(
        limit=limit,
        category_names=tuple(categories or ()),
        category_like=category_like,
        service_name=service_name,
        include_payload=include_payload,
        include_payload_service_fields=True,
    )


def queue_work_request(
    *,
    action: str,
    payload: dict[str, Any],
    category_name: str,
    source: str = "gui",
    priority: int = 80,
    target_rule_id: int | None = None,
    allowed_actions: Sequence[str] | None = None,
    allowed_categories: Sequence[str] | None = None,
    event_message: str | None = None,
) -> int:
    """Insert one work request and its queue event."""
    if allowed_actions is not None and action not in set(allowed_actions):
        raise ValueError("Unsupported work request action.")

    if allowed_categories is not None and category_name not in set(allowed_categories):
        raise ValueError("Unsupported work request category.")

    request_uid = str(uuid.uuid4())
    rendered_payload = json.dumps(payload, sort_keys=True)

    with db.transaction(WORK_REQUEST_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (
                request_uid, source, category_name, action_name,
                target_rule_id, priority, status, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, 'queue', ?)
            """,
            (request_uid, source, category_name, action, target_rule_id, priority, rendered_payload),
        )

        work_request_id = int(cursor.lastrowid)
        
        db.execute_on(
            conn,
            """
            INSERT INTO work_request_events (work_request_id, event_type, message)
            VALUES (?, 'queue', ?)
            """,
            (work_request_id, event_message or f"Queued {category_name} {action}."),
        )
        
        return work_request_id


def get_service_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent ArmFirewall service management work requests."""
    return get_work_requests(
        limit=limit,
        categories=tuple(SERVICE_WORK_REQUEST_CATEGORIES),
    )


def queue_service_work_request(
    action: str,
    payload: dict[str, Any],
    *,
    category_name: str = "SERVICE_MANAGEMENT.OPTIONAL_SERVICES",
) -> int:
    """Queue a service management work request and return its id."""
    return queue_work_request(
        action=action,
        payload=payload,
        category_name=category_name,
        allowed_actions=SERVICE_WORK_REQUEST_ACTIONS,
        allowed_categories=SERVICE_WORK_REQUEST_CATEGORIES,
        event_message=f"Queued service {action}: {payload.get('service_name')}",
    )
