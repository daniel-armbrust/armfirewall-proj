from __future__ import annotations

from typing import Any

import oci

from core.constants import OCI_CONFIG_PATH


def create_object_storage_client(configuration: dict[str, Any]) -> Any:
    """Create an Object Storage client using the selected OCI authentication mode."""
    if configuration["authentication_type"] == "api_key":
        sdk_config = oci.config.from_file(file_location=str(OCI_CONFIG_PATH), profile_name="DEFAULT")
        return oci.object_storage.ObjectStorageClient(sdk_config, timeout=(5, 20))

    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    signer_region = getattr(signer, "region", None)

    if not signer_region:
        raise ValueError("Could not determine the OCI region for Instance Principal.")

    return oci.object_storage.ObjectStorageClient(
        {"region": signer_region}, signer=signer, timeout=(5, 20)
    )
