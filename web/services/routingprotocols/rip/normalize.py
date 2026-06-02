from __future__ import annotations

from web.services.routingprotocols.common import *  # noqa: F403


def rip_iface_names_setting(value: Any) -> list[str]:
    """Normalize RIP interface selection."""
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = []
    selected = []
    for item in items:
        iface_name = str(item or "").strip()
        if not iface_name:
            continue
        if iface_name.lower() == "all" or iface_name == BIRD_ANY_INTERFACE:
            return [BIRD_ANY_INTERFACE]
        selected.append(iface_name)
    if not selected:
        return [BIRD_ANY_INTERFACE]
    valid_names = {str(item.get("name") or "") for item in interfaces()}
    unknown = [item for item in selected if item not in valid_names]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown RIP interface: {unknown[0]}.")
    return list(dict.fromkeys(selected))


def normalize_rip_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate GUI payload for BIRD RIP settings."""
    version = choice_setting(payload.get("version"), field="version", choices=BIRD_RIP_VERSIONS, default="2")
    mode = choice_setting(payload.get("mode"), field="mode", choices=BIRD_RIP_MODES, default="multicast")
    authentication = choice_setting(
        payload.get("authentication"),
        field="authentication",
        choices=BIRD_RIP_AUTHENTICATIONS,
        default="none",
    )
    default_addr = "ff02::9" if version == "ng" else "255.255.255.255" if version == "1" or mode == "broadcast" else "224.0.0.9"
    default_port = 521 if version == "ng" else 520
    multicast_addr = ip_address_setting(payload.get("multicast_addr") or default_addr, field="multicast_addr")
    port = int_setting(payload.get("port"), default=default_port, minimum=1, maximum=65535, field="port")
    password = optional_text(payload.get("password")) or ""
    if version == "ng":
        mode = "multicast"
        multicast_addr = "ff02::9"
        port = 521
    elif version == "1":
        if mode == "multicast":
            raise HTTPException(status_code=400, detail="RIPv1 does not support multicast mode.")
        mode = "broadcast"
        multicast_addr = "255.255.255.255"
        port = 520
    elif version == "2":
        port = 520
        if mode == "broadcast":
            multicast_addr = "255.255.255.255"
        elif multicast_addr != "224.0.0.9":
            raise HTTPException(status_code=400, detail="RIPv2 multicast mode must use multicast address 224.0.0.9.")
    if authentication != "none" and not password:
        raise HTTPException(status_code=400, detail="password is required when authentication is enabled.")
    if authentication == "none":
        password = ""
    return {
        "enabled": bool_setting(payload.get("enabled", True)),
        "version": version,
        "mode": mode,
        "iface_names": rip_iface_names_setting(payload.get("iface_names")),
        "import_policy": import_export_setting(payload.get("import_policy"), field="import_policy", default="all"),
        "export_policy": import_export_setting(payload.get("export_policy"), field="export_policy", default="none"),
        "multicast_addr": multicast_addr,
        "passive": bool_setting(payload.get("passive", False)),
        "port": port,
        "update_time_secs": int_setting(payload.get("update_time_secs"), default=30, minimum=1, maximum=86400, field="update_time_secs"),
        "timeout_time_secs": int_setting(payload.get("timeout_time_secs"), default=180, minimum=1, maximum=86400, field="timeout_time_secs"),
        "garbage_time_secs": int_setting(payload.get("garbage_time_secs"), default=120, minimum=1, maximum=86400, field="garbage_time_secs"),
        "authentication": authentication,
        "password": password,
    }
