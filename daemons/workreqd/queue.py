"""Create work requests for processing by the work request daemon."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any

from core import db
from core.constants import WORK_REQUEST_DB_PATH


def queue_work_request(
    *,
    action: str,
    payload: dict[str, Any],
    category_name: str,
    source: str = "api",
    priority: int = 80,
    target_rule_id: int | None = None,
    allowed_actions: Sequence[str] | None = None,
    allowed_categories: Sequence[str] | None = None,
    event_message: str | None = None,
) -> dict[str, Any]:
    """Insert one validated request for processing by workreqd."""
    if allowed_actions is not None and action not in set(allowed_actions):
        raise ValueError("Unsupported work request action.")
    if allowed_categories is not None and category_name not in set(allowed_categories):
        raise ValueError("Unsupported work request category.")
    if source not in {"gui", "api", "daemon", "system"}:
        raise ValueError("Unsupported work request source.")

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
            (
                request_uid,
                source,
                category_name,
                action,
                target_rule_id,
                priority,
                rendered_payload,
            ),
        )
        work_request_id = int(cursor.lastrowid)
        db.execute_on(
            conn,
            """
            INSERT INTO work_request_events (work_request_id, event_type, message)
            VALUES (?, 'queue', ?)
            """,
            (
                work_request_id,
                event_message or f"Queued {category_name} {action}.",
            ),
        )
    return {
        "work_request_id": work_request_id,
        "request_uid": request_uid,
        "status": "queue",
    }
