from __future__ import annotations

import hashlib
from typing import Any

from oci import regions

from core import db
from core.constants import OCI_CONFIG_PATH, OCI_PRIVATE_KEY_PATH, RUNTIME_SETTINGS_DB_PATH

from . import repository
from .client import create_object_storage_client
from .utils import atomic_write, required_single_line


def get_oci_integration() -> dict[str, str | bool]:
    """Return saved OCI metadata without exposing private material."""
    configuration = repository.get_saved_integration()

    if configuration is None:
        return {"configured": False}

    return {
        "configured": True,
        "authentication_type": str(configuration["authentication_type"]),
        "user_ocid": str(configuration["user_ocid"] or ""),
        "tenancy_ocid": str(configuration["tenancy_ocid"] or ""),
        "region": str(configuration["region"] or ""),
        "fingerprint": str(configuration["fingerprint"] or ""),
    }


def list_oci_regions() -> dict[str, list[str]]:
    """Return all regions supported by the installed OCI SDK."""
    return {"regions": sorted(regions.REGIONS)}


def delete_oci_integration() -> dict[str, bool]:
    """Remove OCI metadata and the associated configuration files."""
    repository.delete_metadata()

    for path in (OCI_CONFIG_PATH, OCI_PRIVATE_KEY_PATH):
        path.unlink(missing_ok=True)

    return {"deleted": True}


def test_oci_integration() -> dict[str, str]:
    """Test OCI authentication through Object Storage GetNamespace."""
    configuration = repository.get_saved_integration()

    if configuration is None:
        raise ValueError("OCI integration is not configured.")

    if configuration["authentication_type"] == "api_key":
        if not configuration["region"] or not configuration["fingerprint"]:
            raise ValueError("OCI region or fingerprint is missing.")

        if not OCI_PRIVATE_KEY_PATH.is_file() or not OCI_PRIVATE_KEY_PATH.read_text(encoding="utf-8").strip():
            raise ValueError("OCI private key file is missing or empty.")

    try:
        create_object_storage_client(configuration).get_namespace()
    except Exception as exc:
        repository.record_authentication_test(status="failed", error=type(exc).__name__[:500])
        raise ValueError("OCI authentication test failed.") from exc

    repository.record_authentication_test(status="success")
    return {"message": "OCI authentication succeeded."}


def save_oci_integration(payload: dict[str, Any]) -> dict[str, str | bool]:
    """Persist OCI metadata in runtime-settings.db and key material on disk."""
    db.verify_database(RUNTIME_SETTINGS_DB_PATH)
    authentication_type = str(payload.get("authentication_type", "")).strip()

    if authentication_type not in {"instance_principal", "api_key"}:
        raise ValueError("Unsupported OCI authentication type.")

    if authentication_type == "instance_principal":
        atomic_write(OCI_CONFIG_PATH, "[DEFAULT]\nauth=instance_principal\n")
        repository.save_metadata(
            authentication_type=authentication_type,
            user_ocid=None,
            tenancy_ocid=None,
            fingerprint=None,
            region=None,
            private_key_filepath=None,
            private_key_sha256=None,
        )

        return {
            "authentication_type": authentication_type,
            "config_path": str(OCI_CONFIG_PATH),
            "private_key_written": False,
        }

    user_ocid = required_single_line(payload, "user_ocid")
    tenancy_ocid = required_single_line(payload, "tenancy_ocid")
    region = required_single_line(payload, "region")
    fingerprint = required_single_line(payload, "fingerprint")
    private_key = str(payload.get("private_key", "")).strip()

    if not private_key:
        raise ValueError("Private key is required.")

    atomic_write(OCI_PRIVATE_KEY_PATH, f"{private_key}\n")
    atomic_write(
        OCI_CONFIG_PATH,
        (
            "[DEFAULT]\n"
            "auth=api_key\n"
            f"user={user_ocid}\n"
            f"tenancy={tenancy_ocid}\n"
            f"region={region}\n"
            f"fingerprint={fingerprint}\n"
            f"key_file={OCI_PRIVATE_KEY_PATH}\n"
        ),
    )
    repository.save_metadata(
        authentication_type=authentication_type,
        user_ocid=user_ocid,
        tenancy_ocid=tenancy_ocid,
        fingerprint=fingerprint,
        region=region,
        private_key_filepath=str(OCI_PRIVATE_KEY_PATH),
        private_key_sha256=hashlib.sha256(private_key.encode("utf-8")).hexdigest(),
    )

    return {
        "authentication_type": authentication_type,
        "config_path": str(OCI_CONFIG_PATH),
        "private_key_written": True,
        "user_ocid": user_ocid,
        "tenancy_ocid": tenancy_ocid,
        "region": region,
        "fingerprint": fingerprint,
    }
