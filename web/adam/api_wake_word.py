"""Authenticated persistence for ADAM wake-word detector profiles."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, Request

from core import db
from core.constants import ADAM_DB_PATH, ADAM_WAKE_ENROLLMENT_SAMPLES
from web import auth
from web.adam.models import AdamWakeWordProfilePayload


def _current_user_id(request: Request) -> int:
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return int(user["id"])


def _validated_profile(payload: AdamWakeWordProfilePayload) -> dict[str, Any]:
    profile_key = payload.profile_key.strip()
    templates = payload.templates
    if not profile_key or len(profile_key) > 64:
        raise HTTPException(status_code=422, detail="Invalid wake-word profile key.")
    if len(templates) != ADAM_WAKE_ENROLLMENT_SAMPLES:
        raise HTTPException(status_code=422, detail="Invalid number of wake-word samples.")
    if not 0.0 < payload.threshold <= 1.0:
        raise HTTPException(status_code=422, detail="Invalid wake-word threshold.")
    if any(
        len(template) != 12
        or any(len(frame) != 10 for frame in template)
        for template in templates
    ):
        raise HTTPException(status_code=422, detail="Invalid wake-word template format.")
    return {
        "profile_key": profile_key,
        "templates": templates,
        "threshold": payload.threshold,
    }


def api_get_wake_word_profile(request: Request, profile_key: str) -> dict[str, Any]:
    """Return the authenticated user's stored wake-word profile."""
    user_id = _current_user_id(request)
    row = db.fetch_one(
        """
        SELECT profile_key, templates_json, threshold, updated_at
          FROM adam_wake_word_profiles
         WHERE user_id = ?
           AND profile_key = ?
        """,
        (user_id, profile_key),
        db_path=ADAM_DB_PATH,
    )
    if not row:
        return {"profile": None}
    try:
        templates = json.loads(row["templates_json"])
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="Stored wake-word profile is invalid.")
    return {
        "profile": {
            "profile_key": row["profile_key"],
            "templates": templates,
            "threshold": row["threshold"],
            "updated_at": row["updated_at"],
        },
    }


def api_save_wake_word_profile(
    request: Request,
    payload: AdamWakeWordProfilePayload,
) -> dict[str, Any]:
    """Replace the authenticated user's wake-word profile."""
    user_id = _current_user_id(request)
    profile = _validated_profile(payload)
    with db.transaction(ADAM_DB_PATH) as connection:
        db.execute_on(
            connection,
            """
            INSERT INTO adam_wake_word_profiles (
                user_id, profile_key, templates_json, threshold
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, profile_key) DO UPDATE SET
                templates_json = excluded.templates_json,
                threshold = excluded.threshold,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                profile["profile_key"],
                json.dumps(profile["templates"], separators=(",", ":")),
                profile["threshold"],
            ),
        )
    return {"profile": profile, "message": "Wake-word profile saved."}
