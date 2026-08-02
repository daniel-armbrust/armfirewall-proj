"""Database state transitions for ADAM training work requests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core import db


def mark_running(
    training_uid: str,
    request_uid: str,
    *,
    db_path: Path,
    normalize_uuid: Callable[[object, str], str],
) -> None:
    """Mark one queued training run as running."""
    updated = db.execute(
        """
        UPDATE adam_training_runs
        SET status = 'running', started_at = CURRENT_TIMESTAMP,
            completed_at = NULL, error_message = NULL
        WHERE training_uid = ? AND work_request_uid = ? AND status = 'queue'
        """,
        (
            normalize_uuid(training_uid, "training_uid"),
            normalize_uuid(request_uid, "request_uid"),
        ),
        db_path=db_path,
    )

    if updated != 1:
        raise ValueError("The ADAM training run is not queued.")


def mark_failed(
    training_uid: str,
    request_uid: str,
    message: str,
    *,
    db_path: Path,
    normalize_uuid: Callable[[object, str], str],
) -> None:
    """Persist a terminal training failure."""
    db.execute(
        """
        UPDATE adam_training_runs
        SET status = 'failed',
            started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
            completed_at = CURRENT_TIMESTAMP,
            error_message = ?, is_active = 0
        WHERE training_uid = ? AND work_request_uid = ?
          AND status IN ('queue', 'running')
        """,
        (
            message[:2000],
            normalize_uuid(training_uid, "training_uid"),
            normalize_uuid(request_uid, "request_uid"),
        ),
        db_path=db_path,
    )
