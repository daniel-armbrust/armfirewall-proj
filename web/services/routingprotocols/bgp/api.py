from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from web.services.routingprotocols.common import *  # noqa: F403
from web.services.routingprotocols.bgp.normalize import normalize_bgp_settings, normalize_bgp_instance_id


def bgp_family_selection(families: set[str]) -> str:
    """Return one GUI family selection from enabled BGP families."""
    normalized = {family for family in families if family in {"ipv4", "ipv6"}}
    if normalized == {"ipv4", "ipv6"}:
        return "ipv4/ipv6"
    if normalized == {"ipv4"}:
        return "ipv4"
    if normalized == {"ipv6"}:
        return "ipv6"
    return "none"


def bgp_enabled_families(settings: dict[str, Any], direction: str) -> set[str]:
    """Return enabled BGP families for one direction."""
    value = str(settings.get(direction) or "none").strip().lower()
    if value == "ipv4/ipv6":
        return {"ipv4", "ipv6"}
    if value in {"ipv4", "ipv6"}:
        return {value}
    return set()


def default_bgp_settings() -> dict[str, Any]:
    """Return default BIRD BGP protocol settings."""
    return {
        "id": None,
        "enabled": False,
        "protocol_name": "",
        "description": "",
        "source_address": "",
        "local_as": "",
        "neighbor_ip": "",
        "neighbor_as": "",
        "iface_name": default_iface_name(),
        "session_type": "auto",
        "direct": True,
        "multihop": False,
        "multihop_ttl": 64,
        "passive": False,
        "password": "",
        "import_policy": "ipv4",
        "export_policy": "none",
    }


def bgp_settings_row_to_dict(row: Any) -> dict[str, Any]:
    """Convert one proto_bgp row to GUI payload format."""
    settings = default_bgp_settings()
    import_families = set()
    export_families = set()
    if bool(row["ipv4_enabled"]):
        if str(row["ipv4_import_policy"] or "none") == "all":
            import_families.add("ipv4")
        if str(row["ipv4_export_policy"] or "none") == "all":
            export_families.add("ipv4")
    if bool(row["ipv6_enabled"]):
        if str(row["ipv6_import_policy"] or "none") == "all":
            import_families.add("ipv6")
        if str(row["ipv6_export_policy"] or "none") == "all":
            export_families.add("ipv6")

    settings.update({
        "id": int(row["id"]),
        "enabled": bool(row["enabled"]),
        "protocol_name": str(row["protocol_name"] or ""),
        "description": str(row["description"] or ""),
        "source_address": str(row["source_address"] or ""),
        "local_as": str(row["local_as"] or ""),
        "neighbor_ip": str(row["neighbor_ip"] or ""),
        "neighbor_as": str(row["neighbor_as"] or ""),
        "iface_name": persisted_iface_name(row["iface_name"]) if "iface_name" in row.keys() else default_iface_name(),
        "session_type": str(row["session_type"] or "auto"),
        "direct": bool(row["direct"]),
        "multihop": bool(row["multihop"]),
        "multihop_ttl": int(row["multihop_ttl"] or 64),
        "passive": bool(row["passive"]),
        "password": str(row["password"] or ""),
        "import_policy": bgp_family_selection(import_families),
        "export_policy": bgp_family_selection(export_families),
    })
    return settings


def list_bgp_settings_from_db() -> list[dict[str, Any]]:
    """Return all persisted BIRD BGP instances from bird.db."""
    db.verify_database(BIRD_DB_PATH)
    with db.connection(BIRD_DB_PATH) as conn:
        rows = db.fetch_all_on(conn, "SELECT * FROM proto_bgp ORDER BY id")
    return [bgp_settings_row_to_dict(row) for row in rows]


def bgp_settings_from_db(instance_id: Any | None = None) -> dict[str, Any]:
    """Return one persisted BIRD BGP instance from bird.db."""
    db.verify_database(BIRD_DB_PATH)
    settings = default_bgp_settings()
    with db.connection(BIRD_DB_PATH) as conn:
        if instance_id is None:
            row = db.fetch_one_on(conn, "SELECT * FROM proto_bgp ORDER BY id LIMIT 1")
        else:
            row = db.fetch_one_on(conn, "SELECT * FROM proto_bgp WHERE id = ?", (normalize_bgp_instance_id(instance_id),))
    if row is None:
        return settings
    return bgp_settings_row_to_dict(row)


def bgp_instance_summary(settings: dict[str, Any]) -> dict[str, Any]:
    """Return a compact BGP instance summary for the GUI table."""
    instance_id = settings.get("id")
    display_name = str(settings.get("protocol_name") or "").strip()
    description = str(settings.get("description") or "").strip()
    neighbor_ip = str(settings.get("neighbor_ip") or "").strip()
    return {
        "id": instance_id,
        "name": display_name or (f"bgp{instance_id}" if instance_id else "bgp"),
        "description": description or "-",
        "neighbor_ip": neighbor_ip or "-",
        "local_as": str(settings.get("local_as") or "-"),
        "neighbor_as": str(settings.get("neighbor_as") or "-"),
        "session_type": str(settings.get("session_type") or "auto"),
        "enabled": bool(settings.get("enabled")),
        "import_policy": str(settings.get("import_policy") or "none"),
        "export_policy": str(settings.get("export_policy") or "none"),
    }


def ensure_unique_bgp_addresses(settings: dict[str, Any], instance_id: Any | None = None) -> None:
    """Ensure source and neighbor addresses are unique across BGP instances."""
    db.verify_database(BIRD_DB_PATH)
    excluded_id = normalize_bgp_instance_id(instance_id) if instance_id is not None else None
    source_address = str(settings.get("source_address") or "").strip()
    neighbor_ip = str(settings.get("neighbor_ip") or "").strip()

    with db.connection(BIRD_DB_PATH) as conn:
        rows = db.fetch_all_on(conn, "SELECT id, source_address, neighbor_ip FROM proto_bgp ORDER BY id")

    for row in rows:
        row_id = int(row["id"])
        if excluded_id is not None and row_id == excluded_id:
            continue
        existing_source = str(row["source_address"] or "").strip()
        existing_neighbor = str(row["neighbor_ip"] or "").strip()
        if source_address and source_address == existing_source:
            raise HTTPException(status_code=400, detail="source_address must be unique among BGP instances.")
        if neighbor_ip and neighbor_ip == existing_neighbor:
            raise HTTPException(status_code=400, detail="neighbor_ip must be unique among BGP instances.")


def save_bgp_settings_to_db(settings: dict[str, Any], instance_id: Any | None = None) -> int:
    """Persist one BIRD BGP instance to bird.db."""
    db.verify_database(BIRD_DB_PATH)
    ensure_unique_bgp_addresses(settings, instance_id)
    import_families = bgp_enabled_families(settings, "import_policy")
    export_families = bgp_enabled_families(settings, "export_policy")
    active_families = import_families | export_families
    values = (
        1 if settings["enabled"] else 0,
        settings["protocol_name"] or None,
        settings["description"] or None,
        settings["source_address"] or None,
        settings["local_as"],
        settings["neighbor_ip"],
        settings["neighbor_as"],
        settings["iface_name"] or None,
        settings["session_type"],
        1 if settings["direct"] else 0,
        1 if settings["multihop"] else 0,
        settings["multihop_ttl"],
        1 if settings["passive"] else 0,
        settings["password"] or None,
        1 if "ipv4" in active_families else 0,
        "all" if "ipv4" in import_families else "none",
        "all" if "ipv4" in export_families else "none",
        1 if "ipv6" in active_families else 0,
        "all" if "ipv6" in import_families else "none",
        "all" if "ipv6" in export_families else "none",
    )
    with db.transaction(BIRD_DB_PATH) as conn:
        if instance_id is None:
            cursor = db.execute_on(
                conn,
                """
                INSERT INTO proto_bgp (
                    enabled, protocol_name, description, source_address, local_as, neighbor_ip, neighbor_as,
                    iface_name, session_type, direct, multihop, multihop_ttl, passive, password,
                    ipv4_enabled, ipv4_import_policy, ipv4_export_policy,
                    ipv6_enabled, ipv6_import_policy, ipv6_export_policy
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            return int(cursor.lastrowid)

        normalized_id = normalize_bgp_instance_id(instance_id)
        updated = db.execute_on(
            conn,
            """
            UPDATE proto_bgp
               SET enabled = ?, protocol_name = ?, description = ?, source_address = ?, local_as = ?, neighbor_ip = ?,
                   neighbor_as = ?, iface_name = ?, session_type = ?, direct = ?, multihop = ?,
                   multihop_ttl = ?, passive = ?, password = ?,
                   ipv4_enabled = ?, ipv4_import_policy = ?, ipv4_export_policy = ?,
                   ipv6_enabled = ?, ipv6_import_policy = ?, ipv6_export_policy = ?
             WHERE id = ?
            """,
            values + (normalized_id,),
        ).rowcount
        if updated == 0:
            raise HTTPException(status_code=404, detail=f"BGP instance {normalized_id} was not found.")
        return normalized_id


def delete_bgp_settings_from_db(instance_id: Any) -> None:
    """Delete one BIRD BGP instance from bird.db."""
    db.verify_database(BIRD_DB_PATH)
    normalized_id = normalize_bgp_instance_id(instance_id)
    with db.transaction(BIRD_DB_PATH) as conn:
        deleted = db.execute_on(conn, "DELETE FROM proto_bgp WHERE id = ?", (normalized_id,)).rowcount
        if deleted == 0:
            raise HTTPException(status_code=404, detail=f"BGP instance {normalized_id} was not found.")


def render_bgp_config(settings: dict[str, Any]) -> str:
    """Render one managed BIRD BGP protocol block."""
    if not settings.get("enabled"):
        return ""
    if not settings.get("local_as") or not settings.get("neighbor_ip") or not settings.get("neighbor_as"):
        return ""

    blocks = []
    display_name = str(settings.get("protocol_name") or "").strip()
    description = str(settings.get("description") or "").strip()
    if display_name:
        blocks.append(f"# {display_name}")
    if description:
        blocks.append(f"# {description}")

    instance_id = settings.get("id")
    protocol_name = f"bgp{instance_id}" if instance_id else "bgp1"
    lines = [f"protocol bgp {protocol_name} {{"]
    lines.append(f"  local as {settings['local_as']};")
    neighbor_ip = str(settings.get("neighbor_ip") or "").split("/", 1)[0].strip()
    lines.append(f"  neighbor {neighbor_ip} as {settings['neighbor_as']};")

    source_address = str(settings.get("source_address") or "").strip()
    if source_address:
        normalized_source = source_address.split("/", 1)[0].strip()
        if normalized_source:
            lines.append(f"  source address {normalized_source};")

    iface_name = str(settings.get("iface_name") or "").strip()
    if iface_name and iface_name != BIRD_ANY_INTERFACE and settings.get("direct") and not settings.get("multihop"):
        lines.append(f'  interface "{iface_name}";')

    if settings.get("multihop"):
        ttl = int(settings.get("multihop_ttl") or 64)
        lines.append(f"  multihop {ttl};")
    elif settings.get("direct"):
        lines.append("  direct;")

    if settings.get("passive"):
        lines.append("  passive yes;")

    password = str(settings.get("password") or "")
    if password:
        lines.append(f'  password "{password}";')

    import_families = bgp_enabled_families(settings, "import_policy")
    export_families = bgp_enabled_families(settings, "export_policy")
    for family in ("ipv4", "ipv6"):
        if family not in import_families and family not in export_families:
            continue
        lines.extend([
            f"  {family} {{",
            f"    import {'all' if family in import_families else 'none'};",
            f"    export {'all' if family in export_families else 'none'};",
            "  };",
        ])

    lines.append("}")
    blocks.append("\n".join(lines))
    return "\n".join(blocks)


def render_bgp_configs(settings_list: list[dict[str, Any]] | None = None) -> str:
    """Render all managed BIRD BGP protocol blocks."""
    blocks = [render_bgp_config(item) for item in (settings_list or [])]
    rendered = [block for block in blocks if block]
    return "\n\n".join(rendered)


def get_bgp_settings(instance_id: Any | None = None) -> dict[str, Any]:
    """Return current BIRD BGP settings, instance list, and preview."""
    instances = list_bgp_settings_from_db()
    selected = bgp_settings_from_db(instance_id) if instance_id is not None else default_bgp_settings()
    return {
        "service": bird_status(),
        "settings": selected,
        "instances": [bgp_instance_summary(item) for item in instances],
        "interfaces": interfaces(),
        "rendered_config": render_bgp_configs(instances),
    }


def add_bgp_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist one new BIRD BGP instance and queue host configuration apply."""
    settings = normalize_bgp_settings(payload)
    instance_id = save_bgp_settings_to_db(settings)
    work_request_id = queue_bird_apply("bgp-settings")
    return get_bgp_settings(instance_id) | {"saved": True, "work_request_id": work_request_id}


def save_bgp_settings(payload: dict[str, Any], instance_id: Any) -> dict[str, Any]:
    """Update one persisted BIRD BGP instance and queue host configuration apply."""
    settings = normalize_bgp_settings(payload)
    normalized_id = save_bgp_settings_to_db(settings, instance_id)
    work_request_id = queue_bird_apply("bgp-settings")
    return get_bgp_settings(normalized_id) | {"saved": True, "work_request_id": work_request_id}


def delete_bgp_settings(instance_id: Any) -> dict[str, Any]:
    """Delete one persisted BIRD BGP instance and queue host configuration apply."""
    delete_bgp_settings_from_db(instance_id)
    work_request_id = queue_bird_apply("bgp-settings")
    return get_bgp_settings() | {"deleted": True, "work_request_id": work_request_id}
