from __future__ import annotations

import ipaddress
import re
from typing import Any

from fastapi import HTTPException

from web.services.routingprotocols.common import *  # noqa: F403

BGP_FAMILY_SELECTIONS = {"none", "ipv4", "ipv6", "ipv4/ipv6"}


def normalize_bgp_instance_id(value: Any) -> int:
    """Normalize one persisted BGP instance id."""
    return int_setting(value, default=0, minimum=1, maximum=2147483647, field="bgp_instance_id")




def bgp_protocol_name_setting(value: Any) -> str:
    """Normalize one optional BGP display name."""
    text = optional_text(value) or ""
    if len(text) > 128:
        raise HTTPException(status_code=400, detail="protocol_name must be 128 characters or fewer.")
    return text


def bgp_source_address_setting(value: Any) -> str:
    """Normalize one optional BGP source address or prefix."""
    raw = optional_text(value) or ""
    if len(raw) > 128:
        raise HTTPException(status_code=400, detail="source_address must be 128 characters or fewer.")
    if not raw:
        return ""
    try:
        ipaddress.ip_address(raw)
        return raw
    except ValueError:
        pass
    try:
        ipaddress.ip_interface(raw)
        return raw
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid BGP source IP/mask.") from exc

def bgp_peer_address_setting(value: Any, *, field: str) -> str:
    """Normalize one BGP peer address, allowing address or prefix notation."""
    raw = optional_text(value) or ""
    if len(raw) > 128:
        raise HTTPException(status_code=400, detail=f"{field} must be 128 characters or fewer.")
    if not raw:
        raise HTTPException(status_code=400, detail=f"{field} is required.")
    try:
        ipaddress.ip_address(raw)
        return raw
    except ValueError:
        pass
    try:
        ipaddress.ip_interface(raw)
        return raw
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field}.") from exc


def bgp_asn_setting(value: Any, *, field: str) -> int:
    """Normalize a BGP ASN field."""
    return int_setting(value, default=0, minimum=1, maximum=4294967295, field=field)


def bgp_iface_name_setting(value: Any, *, direct: bool, multihop: bool) -> str:
    """Normalize one optional BGP interface selection."""
    iface_name = iface_name_setting(value)
    if multihop or not direct:
        return ""
    if not iface_name:
        return default_iface_name()
    valid_names = {str(item.get("name") or "") for item in interfaces()}
    if iface_name not in valid_names and iface_name != BIRD_ANY_INTERFACE:
        raise HTTPException(status_code=400, detail=f"Unknown BGP interface: {iface_name}.")
    return iface_name


def bgp_family_selection_setting(value: Any, *, field: str, default: str) -> str:
    """Normalize one BGP import/export family selection."""
    return choice_setting(value, field=field, choices=BGP_FAMILY_SELECTIONS, default=default)


def normalize_bgp_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate GUI payload for BIRD BGP settings."""
    session_type = choice_setting(payload.get("session_type"), field="session_type", choices=BIRD_BGP_SESSION_TYPES, default="auto")
    local_as = bgp_asn_setting(payload.get("local_as"), field="local_as")
    neighbor_as = bgp_asn_setting(payload.get("neighbor_as"), field="neighbor_as")
    direct = bool_setting(payload.get("direct", True))
    multihop = bool_setting(payload.get("multihop", False))
    multihop_ttl = int_setting(payload.get("multihop_ttl"), default=64, minimum=1, maximum=255, field="multihop_ttl") if multihop else None
    import_policy = bgp_family_selection_setting(payload.get("import_policy"), field="import_policy", default="ipv4")
    export_policy = bgp_family_selection_setting(payload.get("export_policy"), field="export_policy", default="none")
    if import_policy == "none" and export_policy == "none":
        raise HTTPException(status_code=400, detail="At least one address family must be selected in import or export.")
    if session_type == "ibgp" and local_as != neighbor_as:
        raise HTTPException(status_code=400, detail="iBGP requires local_as and neighbor_as to be equal.")
    if session_type == "ebgp" and local_as == neighbor_as:
        raise HTTPException(status_code=400, detail="eBGP requires local_as and neighbor_as to be different.")
    return {
        "enabled": bool_setting(payload.get("enabled", False)),
        "protocol_name": bgp_protocol_name_setting(payload.get("protocol_name")),
        "description": optional_text(payload.get("description")) or "",
        "source_address": bgp_source_address_setting(payload.get("source_address")),
        "local_as": local_as,
        "neighbor_ip": bgp_peer_address_setting(payload.get("neighbor_ip"), field="neighbor_ip"),
        "neighbor_as": neighbor_as,
        "iface_name": bgp_iface_name_setting(payload.get("iface_name"), direct=direct, multihop=multihop),
        "session_type": session_type,
        "direct": direct,
        "multihop": multihop,
        "multihop_ttl": multihop_ttl,
        "passive": bool_setting(payload.get("passive", False)),
        "password": optional_text(payload.get("password")) or "",
        "import_policy": import_policy,
        "export_policy": export_policy,
    }
