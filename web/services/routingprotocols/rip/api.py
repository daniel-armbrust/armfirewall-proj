from __future__ import annotations

from web.services.routingprotocols.common import *  # noqa: F403
from web.services.routingprotocols.rip.normalize import normalize_rip_settings


def default_rip_settings() -> dict[str, Any]:
    """Return default BIRD RIP protocol settings."""
    return {
        "enabled": False,
        "version": "2",
        "mode": "multicast",
        "iface_names": [BIRD_ANY_INTERFACE],
        "import_policy": "all",
        "export_policy": "none",
        "multicast_addr": "224.0.0.9",
        "passive": False,
        "port": 520,
        "update_time_secs": 30,
        "timeout_time_secs": 180,
        "garbage_time_secs": 120,
        "authentication": "none",
        "password": "",
    }


def rip_settings_from_db() -> dict[str, Any]:
    """Return persisted BIRD RIP settings from bird.db."""
    db.verify_database(BIRD_DB_PATH)
    
    settings = default_rip_settings()
    
    with db.connection(BIRD_DB_PATH) as conn:
        row = db.fetch_one_on(conn, "SELECT * FROM proto_rip ORDER BY id LIMIT 1")
    
    if row is None:
        return settings
    
    iface_names = [BIRD_ANY_INTERFACE]
    
    if "iface_names" in row.keys():
        try:
            loaded_iface_names = json.loads(str(row["iface_names"] or "[]"))
        except json.JSONDecodeError:
            loaded_iface_names = []
    
        if isinstance(loaded_iface_names, list):
            iface_names = [str(item) for item in loaded_iface_names if str(item).strip()] or [BIRD_ANY_INTERFACE]
    
    return {
        "enabled": bool(row["enabled"]),
        "version": str(row["version"]),
        "mode": str(row["mode"]),
        "iface_names": iface_names,
        "import_policy": str(row["import_policy"] if "import_policy" in row.keys() else "all"),
        "export_policy": str(row["export_policy"] if "export_policy" in row.keys() else "none"),
        "multicast_addr": str(row["multicast_addr"]),
        "passive": bool(row["passive"]),
        "port": int(row["port"]),
        "update_time_secs": int(row["update_time_secs"]),
        "timeout_time_secs": int(row["timeout_time_secs"]),
        "garbage_time_secs": int(row["garbage_time_secs"]),
        "authentication": str(row["authentication"]),
        "password": str(row["password"] or ""),
    }


def save_rip_settings_to_db(settings: dict[str, Any]) -> None:
    """Persist BIRD RIP settings to bird.db."""
    db.verify_database(BIRD_DB_PATH)
    
    with db.transaction(BIRD_DB_PATH) as conn:
        existing = db.fetch_one_on(conn, "SELECT id FROM proto_rip ORDER BY id LIMIT 1")
    
        values = (
            settings["version"], settings["mode"], json.dumps(settings["iface_names"], sort_keys=True),
            settings["import_policy"], settings["export_policy"],
            settings["multicast_addr"], 1 if settings["passive"] else 0,
            settings["port"], settings["update_time_secs"], settings["timeout_time_secs"], settings["garbage_time_secs"],
            settings["authentication"], settings["password"] or None, 1 if settings["enabled"] else 0,
        )
    
        if existing is None:
            db.execute_on(
                conn,
                """
                INSERT INTO proto_rip (
                    version, mode, iface_names, import_policy, export_policy, multicast_addr, passive, port, update_time_secs,
                    timeout_time_secs, garbage_time_secs, authentication, password, enabled
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            return
    
        db.execute_on(
            conn,
            """
            UPDATE proto_rip
               SET version = ?, mode = ?, iface_names = ?, import_policy = ?, export_policy = ?,
                   multicast_addr = ?, passive = ?, port = ?, update_time_secs = ?,
                   timeout_time_secs = ?, garbage_time_secs = ?, authentication = ?, password = ?, enabled = ?
             WHERE id = ?
            """,
            (*values, int(existing["id"])),
        )


def render_rip_config(settings: dict[str, Any]) -> str:
    """Render the managed BIRD RIP protocol block."""
    if not settings["enabled"]:
        return ""
    
    channel_family = "ipv6" if settings["version"] == "ng" else "ipv4"
    passive_line = "    passive yes;" if settings["passive"] else "    passive no;"
    iface_names = settings.get("iface_names") or [BIRD_ANY_INTERFACE]
    iface_pattern = '", "'.join(str(item).replace('"', '\"') for item in iface_names)
    auth_lines = ""
    
    if settings["authentication"] != "none":
        auth_lines = (
            f"    authentication {settings['authentication']};\n"
            f"    password \"{settings['password']}\";\n"
        )
    
    return (
        "protocol rip {\n"
        f"  {channel_family} {{\n"
        f"    import {settings['import_policy']};\n"
        f"    export {settings['export_policy']};\n"
        "  };\n"
        f"  interface \"{iface_pattern}\" {{\n"
        f"    mode {settings['mode']};\n"
        f"    update time {settings['update_time_secs']};\n"
        f"    timeout time {settings['timeout_time_secs']};\n"
        f"    garbage time {settings['garbage_time_secs']};\n"
        f"{passive_line}\n"
        f"{auth_lines}"
        "  };\n"
        "}"
    )


def get_rip_settings() -> dict[str, Any]:
    """Return current BIRD RIP protocol settings."""
    settings = rip_settings_from_db()
    
    return {
        "service": bird_status(),
        "settings": settings,
        "rendered_config": render_rip_config(settings),
    }


def save_rip_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist BIRD RIP protocol settings and queue host configuration apply."""
    settings = normalize_rip_settings(payload)
    
    save_rip_settings_to_db(settings)
    
    work_request_id = queue_bird_apply("rip-settings")
    
    return get_rip_settings() | {"saved": True, "work_request_id": work_request_id}


def latest_rip_protocol_name(conn: db.Connection) -> str | None:
    """Return active RIP protocol name from the latest structured BIRD protocol snapshot."""
    run = db.fetch_one_on(
        conn,
        """
        SELECT id
        FROM diagnostic_command_run
        WHERE command = '/usr/sbin/birdcl show protocols'
        ORDER BY collected_at DESC, id DESC
        LIMIT 1
        """,
    )
    
    if run is None:
        return None
    
    row = db.fetch_one_on(
        conn,
        """
        SELECT name
        FROM diagnostic_protocol
        WHERE command_id = ? AND lower(proto) = 'rip'
        ORDER BY name
        LIMIT 1
        """,
        (int(run["id"]),),
    )
    
    return str(row["name"]) if row is not None else None


def latest_rip_routes(conn: db.Connection, table_name: str) -> list[dict[str, Any]]:
    """Return the current structured RIP route snapshot."""
    if table_name not in {"rip_imported_routes", "rip_exported_routes"}:
        raise ValueError(f"Unsupported RIP route table: {table_name}")
    
    try:
        rows = db.fetch_all_on(
            conn,
            f"""
            SELECT table_name, route_prefix, route_type, source_protocol, since, selected, metric,
                   next_hop, iface_name, raw_route, raw_detail, collected_at
            FROM {table_name}
            ORDER BY route_prefix, iface_name, next_hop
            """,
        )
    except db.DatabaseError:
        return []
    
    return [
        {
            "table_name": row["table_name"],
            "route_prefix": str(row["route_prefix"]),
            "route_type": row["route_type"],
            "source_protocol": row["source_protocol"],
            "since": row["since"],
            "selected": bool(row["selected"]),
            "metric": row["metric"],
            "next_hop": row["next_hop"],
            "iface_name": row["iface_name"],
            "raw_route": row["raw_route"],
            "raw_detail": row["raw_detail"],
            "collected_at": str(row["collected_at"]),
        }
        for row in rows
    ]


def rip_protocol_enabled(conn: db.Connection) -> bool:
    """Return whether the persisted RIP protocol is enabled."""
    row = db.fetch_one_on(conn, "SELECT enabled FROM proto_rip ORDER BY id LIMIT 1")
    
    return bool(row["enabled"]) if row is not None else False


def get_rip_diagnostics() -> dict[str, Any]:
    """Return latest RIP diagnostics snapshots collected by collectord."""
    db.verify_database(BIRD_DB_PATH)
    
    with db.connection(BIRD_DB_PATH) as conn:
        if not rip_protocol_enabled(conn):
            return {"last_run": None, "sections": [], "enabled": False, "active": False}
        
        rip_protocol_name = latest_rip_protocol_name(conn)
        
        if not rip_protocol_name:
            return {"last_run": None, "sections": [], "enabled": True, "active": False}
        
        commands = [
            {"key": "status", "title": "Status", "command": f"/usr/sbin/birdcl show protocols all {rip_protocol_name}"},
            {"key": "learned_routes", "title": "Learned Routes", "command": f"/usr/sbin/birdcl show route protocol {rip_protocol_name}"},
            {"key": "exported_routes", "title": "Exported Routes", "command": f"/usr/sbin/birdcl show route export {rip_protocol_name}"},
        ]
        
        sections = []
        
        for item in commands:
            section = latest_diagnostic_command(conn, item["command"])
            section["key"] = item["key"]
            section["title"] = item["title"]
            
            if item["key"] == "learned_routes":
                section["routes"] = latest_rip_routes(conn, "rip_imported_routes")
            elif item["key"] == "exported_routes":
                section["routes"] = latest_rip_routes(conn, "rip_exported_routes")
            
            sections.append(section)
    
    latest_runs = [section["last_run"] for section in sections if section.get("last_run")]
    latest_run = max(latest_runs, key=lambda run: (run["collected_at"], run["id"])) if latest_runs else None
    
    return {
        "last_run": latest_run,
        "sections": sections,
        "enabled": True,
        "active": True,
    }
