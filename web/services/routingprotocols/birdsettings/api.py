from __future__ import annotations

from web.services.routingprotocols.common import *  # noqa: F403
from web.services.routingprotocols.bgp.api import default_bgp_settings, list_bgp_settings_from_db, render_bgp_configs
from web.services.routingprotocols.birdsettings.normalize import normalize_global_settings
from web.services.routingprotocols.rip.api import default_rip_settings, render_rip_config, rip_settings_from_db


def default_global_settings() -> dict[str, Any]:
    """Return default global BIRD daemon settings for the GUI."""
    return {
        "router_id": default_router_id(),
        "hostname": default_hostname(),
        "debug_enabled": False,
        "log_syslog": True,
        "kernel": {
            "enabled": True,
            "route_table": 254,
            "learn": "all",
            "channel_family": "ipv4",
            "channel_table_name": BIRD_DEFAULT_CHANNEL_TABLE_NAME,
            "import_policy": "all",
            "export_policy": "none",
            "metric": 32,
            "scan_time_secs": 10,
            "persist": True,
        },
        "device": {
            "enabled": True,
            "scan_time_secs": 10,
            "iface_name": "",
        },
        "direct": {
            "enabled": True,
            "iface_name": "",
        },
    }


def settings_from_db() -> dict[str, Any]:
    """Return persisted BIRD settings from bird.db."""
    db.verify_database(BIRD_DB_PATH)
    
    settings = default_global_settings()
    path = BIRD_CONFIG_PATH
    
    if path.exists():
        settings |= parse_router_settings(path.read_text(encoding="utf-8"))
        settings["router_id"] = default_router_id()
        settings["hostname"] = default_hostname()

    with db.connection(BIRD_DB_PATH) as conn:
        global_cfg = db.fetch_one_on(conn, "SELECT * FROM global_cfg WHERE id = 1")
    
        if global_cfg is not None:
            saved_router_id = str(global_cfg["router_id"] or "").strip()
            settings["router_id"] = default_router_id() if saved_router_id in {"", BIRD_DEFAULT_ROUTER_ID} else saved_router_id
            settings["hostname"] = str(global_cfg["hostname"] or default_hostname())
            settings["debug_enabled"] = bool(global_cfg["debug_enabled"]) if "debug_enabled" in global_cfg.keys() else False

        kernel = db.fetch_one_on(
            conn,
            """
            SELECT k.*, c.family AS channel_family, c.table_name AS channel_table_name,
                   c.import_policy, c.export_policy
            FROM proto_kernel k
            JOIN channel c ON c.id = k.channel_id
            ORDER BY k.id
            LIMIT 1
            """,
        )

        if kernel is not None:
            settings["kernel"] = {
                "enabled": bool(kernel["enabled"]),
                "route_table": int(kernel["route_table"]),
                "learn": kernel["learn"],
                "channel_family": str(kernel["channel_family"]),
                "channel_table_name": str(kernel["channel_table_name"] or BIRD_DEFAULT_CHANNEL_TABLE_NAME),
                "import_policy": str(kernel["import_policy"]),
                "export_policy": str(kernel["export_policy"]),
                "metric": int(kernel["metric"]),
                "scan_time_secs": int(kernel["scan_time_secs"]),
                "persist": bool(kernel["persist"]),
            }
        else:
            tables = routing_tables()

            if tables:
                settings["kernel"]["route_table"] = int(tables[0]["table_id"])

        device = db.fetch_one_on(conn, "SELECT * FROM proto_device ORDER BY id LIMIT 1")
        
        if device is not None:
            settings["device"] = {
                "enabled": bool(device["enabled"]),
                "scan_time_secs": int(device["scan_time_secs"]),
                "iface_name": persisted_iface_name(device["iface_name"]),
            }
        else:
            settings["device"]["iface_name"] = default_iface_name()

        direct = db.fetch_one_on(conn, "SELECT * FROM proto_direct ORDER BY id LIMIT 1")
        
        if direct is not None:
            settings["direct"] = {
                "enabled": bool(direct["enabled"]),
                "iface_name": persisted_iface_name(direct["iface_name"]),
            }
        else:
            settings["direct"]["iface_name"] = default_iface_name()
    
    return settings


def get_or_create_channel(conn: db.Connection, kernel: dict[str, Any]) -> int:
    """Return a channel id matching the kernel channel settings."""
    table_name = kernel["channel_table_name"] or None
    current = db.fetch_one_on(
        conn,
        """
        SELECT id
        FROM channel
        WHERE family = ?
          AND table_name IS ?
          AND import_policy = ?
          AND export_policy = ?
        """,
        (kernel["channel_family"], table_name, kernel["import_policy"], kernel["export_policy"]),
    )

    if current is not None:
        return int(current["id"])
    
    cursor = db.execute_on(
        conn,
        """
        INSERT INTO channel (family, table_name, import_policy, export_policy)
        VALUES (?, ?, ?, ?)
        """,
        (kernel["channel_family"], table_name, kernel["import_policy"], kernel["export_policy"]),
    )

    return int(cursor.lastrowid)


def save_settings_to_db(settings: dict[str, Any]) -> None:
    """Persist BIRD settings to bird.db."""
    db.verify_database(BIRD_DB_PATH)

    with db.transaction(BIRD_DB_PATH) as conn:
        updated = db.execute_on(
            conn,
            """
            UPDATE global_cfg
               SET router_id = ?, hostname = ?, debug_enabled = ?
             WHERE id = 1
            """,
            (settings["router_id"], settings["hostname"], 1 if settings["debug_enabled"] else 0),
        ).rowcount

        if updated == 0:
            db.execute_on(
                conn,
                "INSERT INTO global_cfg (id, router_id, hostname, debug_enabled) VALUES (1, ?, ?, ?)",
                (settings["router_id"], settings["hostname"], 1 if settings["debug_enabled"] else 0),
            )

        kernel = settings["kernel"]
        channel_id = get_or_create_channel(conn, kernel)
        existing_kernel = db.fetch_one_on(conn, "SELECT id FROM proto_kernel ORDER BY id LIMIT 1")
        kernel_values = (
            kernel["route_table"], kernel["learn"], channel_id, kernel["metric"],
            kernel["scan_time_secs"], 1 if kernel["persist"] else 0, 1 if kernel["enabled"] else 0,
        )

        if existing_kernel is None:
            db.execute_on(
                conn,
                """
                INSERT INTO proto_kernel (route_table, learn, channel_id, metric, scan_time_secs, persist, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                kernel_values,
            )
        else:
            db.execute_on(
                conn,
                """
                UPDATE proto_kernel
                   SET route_table = ?, learn = ?, channel_id = ?, metric = ?,
                       scan_time_secs = ?, persist = ?, enabled = ?
                 WHERE id = ?
                """,
                (*kernel_values, int(existing_kernel["id"])),
            )

        db.execute_on(conn, "DELETE FROM proto_device")
        device = settings["device"]

        if device["iface_name"]:
            db.execute_on(
                conn,
                "INSERT INTO proto_device (scan_time_secs, iface_name, enabled) VALUES (?, ?, ?)",
                (device["scan_time_secs"], device["iface_name"], 1 if device["enabled"] else 0),
            )

        db.execute_on(conn, "DELETE FROM proto_direct")
        direct = settings["direct"]

        if direct["iface_name"]:
            db.execute_on(
                conn,
                "INSERT INTO proto_direct (iface_name, enabled) VALUES (?, ?)",
                (direct["iface_name"], 1 if direct["enabled"] else 0),
            )


def channel_table_declarations(settings: dict[str, Any]) -> list[str]:
    """Render top-level BIRD table declarations needed by channel table references."""
    kernel = settings.get("kernel") or {}
    table_name = str(kernel.get("channel_table_name") or "").strip()
    
    if not kernel.get("enabled") or not table_name or table_name == BIRD_DEFAULT_CHANNEL_TABLE_NAME:
        return []
    
    families = ("ipv4", "ipv6") if kernel["channel_family"] == "ipv4/ipv6" else (kernel["channel_family"],)
    
    return [f"{family} table {table_name};" for family in families]


def channel_block(settings: dict[str, Any], family: str | None = None) -> str:
    """Render one or more BIRD channel blocks."""
    families = (family,) if family else ("ipv4", "ipv6") if settings["channel_family"] == "ipv4/ipv6" else (settings["channel_family"],)
    table_name = str(settings.get("channel_table_name") or "").strip()
    table_line = f"    table {table_name};\n" if table_name and table_name != BIRD_DEFAULT_CHANNEL_TABLE_NAME else ""
    
    return "".join(
        (
            f"  {item} {{\n"
            f"{table_line}"
            f"    import {settings['import_policy']};\n"
            f"    export {settings['export_policy']};\n"
            "  };\n"
        )
        for item in families
    )


def render_kernel_config(kernel: dict[str, Any]) -> str:
    """Render BIRD kernel protocol blocks.

    BIRD accepts IPv4 and IPv6 kernel channels, but when a kernel table is
    configured they must be rendered as separate protocol instances.
    """
    if not kernel["enabled"]:
        return ""
    
    families = ("ipv4", "ipv6") if kernel["channel_family"] == "ipv4/ipv6" else (kernel["channel_family"],)
    learn_line = "  learn all;\n" if kernel["learn"] == "all" else ""
    persist_line = "  persist;\n" if kernel["persist"] else ""
    blocks = []
    
    for family in families:
        suffix = "4" if family == "ipv4" else "6"
        blocks.append(
            f"protocol kernel kernel{suffix} {{\n"
            f"  kernel table {kernel['route_table']};\n"
            f"{learn_line}"
            f"{persist_line}"
            f"  metric {kernel['metric']};\n"
            f"  scan time {kernel['scan_time_secs']};\n"
            f"{channel_block(kernel, family)}"
            "}"
        )

    return "\n\n".join(blocks)


def render_global_config(settings: dict[str, Any], rip_settings: dict[str, Any] | None = None, bgp_settings: list[dict[str, Any]] | None = None) -> str:
    """Render a managed BIRD global configuration."""
    blocks = [
        "# Managed by ArmFirewall Network / Routing Protocols.",
        f"router id {settings['router_id']};",
        f"hostname \"{settings['hostname']}\";",
        "log stderr all;",
        *( ["debug protocols all;"] if settings.get("debug_enabled") else [] ),
        *channel_table_declarations(settings),
        "",
    ]

    device = settings["device"]

    if device["enabled"] and device["iface_name"]:
        blocks.extend([
            "protocol device {",
            f"  scan time {device['scan_time_secs']};",
            f"  interface \"{device['iface_name']}\";",
            "}",
            "",
        ])

    direct = settings["direct"]

    if direct["enabled"] and direct["iface_name"]:
        blocks.extend([
            "protocol direct {",
            f"  interface \"{direct['iface_name']}\";",
            "  ipv4;",
            "  ipv6;",
            "}",
            "",
        ])

    kernel_block = render_kernel_config(settings["kernel"])

    if kernel_block:
        blocks.append(kernel_block)

    rip_block = render_rip_config(rip_settings or default_rip_settings())
    if rip_block:
        blocks.extend(["", rip_block])

    bgp_block = render_bgp_configs(bgp_settings or ([] if bgp_settings is not None else [default_bgp_settings()]))
    if bgp_block:
        blocks.extend(["", bgp_block])

    return "\n".join(blocks).rstrip() + "\n"


def get_global_settings() -> dict[str, Any]:
    """Return current BIRD global daemon settings and status."""
    settings = settings_from_db()
    path = BIRD_CONFIG_PATH
    
    return {
        "service": bird_status(),
        "bird_version": bird_version(),
        "config_path": str(path),
        "exists": path.exists(),
        "settings": settings,
        "routing_tables": routing_tables(),
        "interfaces": interfaces(),
        "rendered_config": render_global_config(settings, rip_settings_from_db(), list_bgp_settings_from_db()),
    }


def save_global_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist BIRD global daemon settings and queue host configuration apply."""
    settings = normalize_global_settings(payload)
    
    save_settings_to_db(settings)
    
    work_request_id = queue_bird_apply("global-settings")

    return get_global_settings() | {"saved": True, "work_request_id": work_request_id}


def get_bird_diagnostics() -> dict[str, Any]:
    """Return the latest BIRD diagnostics snapshot collected by collectord."""
    db.verify_database(BIRD_DB_PATH)

    with db.connection(BIRD_DB_PATH) as conn:
        run = db.fetch_one_on(
            conn,
            """
            SELECT id, command, exit_code, stdout, stderr, duration_ms, collected_at
            FROM diagnostic_command_run
            WHERE command LIKE '% show protocols'
            ORDER BY collected_at DESC, id DESC
            LIMIT 1
            """,
        )

        if run is None:
            return {
                "last_run": None,
                "protocols": [],
                "raw_output": "",
                "error_output": "",
            }
        
        protocols = db.rows_to_dicts(db.execute_on(
            conn,
            """
            SELECT name, proto, table_name, state, since, info, raw_line, collected_at
            FROM diagnostic_protocol
            WHERE command_id = ?
            ORDER BY id
            """,
            (int(run["id"]),),
        ).fetchall())

    return {
        "last_run": {
            "id": int(run["id"]),
            "command": str(run["command"]),
            "exit_code": int(run["exit_code"]),
            "duration_ms": run["duration_ms"],
            "collected_at": str(run["collected_at"]),
        },
        "protocols": protocols,
        "raw_output": str(run["stdout"] or ""),
        "error_output": str(run["stderr"] or ""),
    }


def read_bird_logs(*, max_lines: int = 300) -> dict[str, Any]:
    """Return recent BIRD supervisord stdout and stderr log lines newest first."""
    started = time.monotonic()

    sources = (
        ("stdout", BIRD_LOG_PATH),
        ("stderr", BIRD_ERR_LOG_PATH),
    )
    
    files = []
    entries: list[tuple[int, str, int, str]] = []
    sequence = 0
    timestamp_pattern = re.compile(r"^bird:\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)")
    
    for label, path in sources:
        exists = path.exists()
        source_lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if exists else []
        files.append({"name": label, "path": str(path), "exists": exists, "line_count": len(source_lines)})
    
        for line in source_lines:
            match = timestamp_pattern.match(line)
            timestamp = match.group(1) if match else ""
            has_timestamp = 0 if timestamp else 1
            entries.append((has_timestamp, timestamp, sequence, line))
            sequence += 1

    entries.sort(key=lambda item: (item[0], item[1], item[2]))
    lines = [line for _, _, _, line in reversed(entries[-max_lines:])]
    
    return {
        "path": str(BIRD_LOG_PATH),
        "stderr_path": str(BIRD_ERR_LOG_PATH),
        "exists": any(item["exists"] for item in files),
        "files": files,
        "lines": lines,
        "line_count": len(lines),
        "updated_at": db.sqlite_timestamp(),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
