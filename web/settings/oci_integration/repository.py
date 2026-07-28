from __future__ import annotations

from typing import Any

from core import db
from core.constants import RUNTIME_SETTINGS_DB_PATH


def get_saved_integration() -> dict[str, Any] | None:
    """Return persisted OCI metadata from the installed runtime settings database."""
    return db.fetch_one(
        """
        SELECT authentication_type, user_ocid, tenancy_ocid, fingerprint, region,
               profile_name, private_key_filepath, private_key_sha256, enabled
          FROM oci_integration
         WHERE id = 1
        """,
        db_path=RUNTIME_SETTINGS_DB_PATH,
    )


def save_metadata(
    *,
    authentication_type: str,
    user_ocid: str | None,
    tenancy_ocid: str | None,
    fingerprint: str | None,
    region: str | None,
    private_key_filepath: str | None,
    private_key_sha256: str | None,
) -> None:
    """Persist non-secret OCI integration metadata in runtime-settings.db."""
    with db.transaction(RUNTIME_SETTINGS_DB_PATH) as conn:
        db.execute_on(
            conn,
            """
            INSERT INTO oci_integration (
                id, authentication_type, user_ocid, tenancy_ocid, fingerprint, region,
                profile_name, private_key_filepath, private_key_sha256, enabled
            ) VALUES (1, ?, ?, ?, ?, ?, 'DEFAULT', ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET
                authentication_type = excluded.authentication_type,
                user_ocid = excluded.user_ocid,
                tenancy_ocid = excluded.tenancy_ocid,
                fingerprint = excluded.fingerprint,
                region = excluded.region,
                profile_name = excluded.profile_name,
                private_key_filepath = excluded.private_key_filepath,
                private_key_sha256 = excluded.private_key_sha256,
                enabled = excluded.enabled,
                last_authentication_test_at = NULL,
                last_authentication_test_status = NULL,
                last_authentication_test_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                authentication_type,
                user_ocid,
                tenancy_ocid,
                fingerprint,
                region,
                private_key_filepath,
                private_key_sha256,
            ),
        )


def delete_metadata() -> None:
    """Remove the persisted OCI metadata."""
    with db.transaction(RUNTIME_SETTINGS_DB_PATH) as conn:
        db.execute_on(conn, "DELETE FROM oci_integration WHERE id = 1")


def record_authentication_test(*, status: str, error: str | None = None) -> None:
    """Record the outcome of one OCI authentication test."""
    with db.transaction(RUNTIME_SETTINGS_DB_PATH) as conn:
        db.execute_on(
            conn,
            """
            UPDATE oci_integration
               SET last_authentication_test_at = CURRENT_TIMESTAMP,
                   last_authentication_test_status = ?,
                   last_authentication_test_error = ?
             WHERE id = 1
            """,
            (status, error),
        )
