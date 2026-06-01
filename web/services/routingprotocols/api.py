from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from core import db
from core.system import get_hostname
from core.constants import (
    BIRD_ANY_INTERFACE,
    BIRD_CHANNEL_FAMILIES,
    BIRD_CONFIG_PATH,
    BIRD_DB_PATH,
    BIRD_DEFAULT_CHANNEL_TABLE_NAME,
    BIRD_DEFAULT_HOSTNAME,
    BIRD_DEFAULT_ROUTER_ID,
    BIRD_IMPORT_EXPORT_VALUES,
    BIRD_LOG_PATH,
    BIRD_RIP_AUTHENTICATIONS,
    BIRD_RIP_MODES,
    BIRD_RIP_VERSIONS,
    IFACE_DB_PATH,
    POLICY_ROUTING_DB_PATH,
)
from web.services.api import service_installed, service_status_by_name


def bird_config_path() -> Path:
    """Return the ArmFirewall-managed BIRD configuration path."""
    return BIRD_CONFIG_PATH


def ensure_bird_db() -> None:
    """Verify the ArmFirewall-managed BIRD database exists."""
    db.verify_database(BIRD_DB_PATH)


def bird_service_installed() -> bool:
    """Return whether the BIRD routing daemon is installed."""
    return service_installed("bird")


def bird_version() -> str:
    """Return the installed BIRD daemon version."""
    for command in (["bird", "--version"], ["/usr/sbin/bird", "--version"]):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        output = (result.stdout or result.stderr or "").strip()
        if output:
            first_line = output.splitlines()[0]
            match = re.search(r"(\d+(?:\.\d+)+)", first_line)
            return match.group(1) if match else first_line
    return "-"


def bird_status() -> dict[str, Any]:
    """Return the persisted BIRD optional service status."""
    try:
        return service_status_by_name("bird")
    except ValueError:
        return {
            "name": "bird",
            "display_name": "BIRD Routing Daemon",
            "installed": False,
            "state": "NOT INSTALLED",
            "details": "Missing from service catalog.",
        }


def int_setting(value: Any, *, default: int, minimum: int, maximum: int, field: str) -> int:
    """Normalize one bounded integer setting."""
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be an integer.") from exc
    if parsed < minimum or parsed > maximum:
        raise HTTPException(status_code=400, detail=f"{field} must be between {minimum} and {maximum}.")
    return parsed


def bool_setting(value: Any) -> bool:
    """Normalize a boolean-ish payload field."""
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def import_export_setting(value: Any, *, field: str, default: str) -> str:
    """Normalize one BIRD import/export policy value."""
    text = str(value if value not in (None, "") else default).strip().lower()
    if text not in BIRD_IMPORT_EXPORT_VALUES:
        raise HTTPException(status_code=400, detail=f"{field} must be all or none.")
    return text


def channel_family_setting(value: Any) -> str:
    """Normalize one BIRD channel address family."""
    family = str(value or "ipv4").strip().lower()
    if family not in BIRD_CHANNEL_FAMILIES:
        raise HTTPException(status_code=400, detail="channel family must be ipv4, ipv6 or ipv4/ipv6.")
    return family


def optional_text(value: Any) -> str | None:
    """Return a stripped optional text value."""
    text = str(value or "").strip()
    return text or None


def iface_name_setting(value: Any) -> str:
    """Normalize an optional BIRD interface selector."""
    text = optional_text(value)
    if text is None:
        return ""
    if text.lower() == "any" or text == BIRD_ANY_INTERFACE:
        return BIRD_ANY_INTERFACE
    return text


def required_text(value: Any, *, field: str) -> str:
    """Return a stripped required text value."""
    text = optional_text(value)
    if text is None:
        raise HTTPException(status_code=400, detail=f"{field} is required.")
    return text


def router_id_setting(value: Any) -> str:
    """Normalize and validate the BIRD router id."""
    text = str(value or BIRD_DEFAULT_ROUTER_ID).strip()
    try:
        ipaddress.IPv4Address(text)
    except ipaddress.AddressValueError as exc:
        raise HTTPException(status_code=400, detail="router_id must be an IPv4 address.") from exc
    return text


def hostname_setting(value: Any) -> str:
    """Normalize and validate the BIRD hostname."""
    text = str(value or BIRD_DEFAULT_HOSTNAME).strip()
    if len(text) > 253:
        raise HTTPException(status_code=400, detail="hostname must be 253 characters or fewer.")
    labels = text.rstrip(".").split(".")
    label_pattern = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
    if not labels or any(not label_pattern.match(label) for label in labels):
        raise HTTPException(status_code=400, detail="hostname must be a valid hostname.")
    return text


def ip_address_setting(value: Any, *, field: str) -> str:
    """Normalize and validate an IP address field."""
    text = required_text(value, field=field)
    try:
        ipaddress.ip_address(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be an IP address.") from exc
    return text


def choice_setting(value: Any, *, field: str, choices: set[str], default: str) -> str:
    """Normalize a constrained text choice."""
    text = str(value if value not in (None, "") else default).strip().lower()
    if text not in choices:
        allowed = ", ".join(sorted(choices))
        raise HTTPException(status_code=400, detail=f"{field} must be one of: {allowed}.")
    return text


def default_hostname() -> str:
    """Return a stable default hostname for BIRD global settings."""
    try:
        return hostname_setting(get_hostname())
    except HTTPException:
        return BIRD_DEFAULT_HOSTNAME


def parse_router_settings(text: str) -> dict[str, Any]:
    """Extract global router settings from an existing BIRD config."""
    settings = {"router_id": BIRD_DEFAULT_ROUTER_ID, "hostname": default_hostname(), "log_syslog": True}
    router_match = re.search(r"^\s*router\s+id\s+([0-9.]+)\s*;", text, re.MULTILINE)
    hostname_match = re.search(r'^\s*hostname\s+"([^"]+)"\s*;', text, re.MULTILINE)
    log_match = re.search(r"^\s*log\s+syslog\s+(all|off)\s*;", text, re.MULTILINE)
    if router_match:
        settings["router_id"] = router_match.group(1)
    if hostname_match:
        settings["hostname"] = hostname_match.group(1)
    if log_match:
        settings["log_syslog"] = log_match.group(1) == "all"
    return settings


def routing_tables() -> list[dict[str, Any]]:
    """Return policy routing table choices for BIRD kernel protocol."""
    try:
        with db.connection(POLICY_ROUTING_DB_PATH) as conn:
            columns = db.fetch_all_on(conn, "PRAGMA table_info(routing_tables)")
            has_pending_delete = any(column["name"] == "pending_delete" for column in columns)
            delete_filter = "AND pending_delete = 0" if has_pending_delete else ""
            return db.rows_to_dicts(db.fetch_all_on(
                conn,
                f"""
                SELECT id, table_id, table_name
                FROM routing_tables
                WHERE enabled = 1 {delete_filter}
                ORDER BY table_id
                """,
            ))
    except (FileNotFoundError, db.DatabaseError):
        return [
            {"id": None, "table_id": 253, "table_name": "default"},
            {"id": None, "table_id": 254, "table_name": "main"},
            {"id": None, "table_id": 255, "table_name": "local"},
        ]


def interfaces() -> list[dict[str, Any]]:
    """Return interface choices for BIRD device/direct protocols."""
    try:
        with db.connection(IFACE_DB_PATH) as conn:
            return db.rows_to_dicts(db.fetch_all_on(
                conn,
                """
                SELECT id, name, description, role
                FROM ifaces
                ORDER BY CASE role WHEN 'LAN' THEN 0 WHEN 'WAN' THEN 1 ELSE 2 END, name
                """,
            ))
    except (FileNotFoundError, db.DatabaseError):
        return []


def default_iface_name() -> str:
    """Return the first known interface name."""
    items = interfaces()
    return str(items[0]["name"]) if items else ""


def default_global_settings() -> dict[str, Any]:
    """Return default global BIRD daemon settings for the GUI."""
    return {
        "router_id": BIRD_DEFAULT_ROUTER_ID,
        "hostname": default_hostname(),
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
    ensure_bird_db()
    settings = default_global_settings()
    path = bird_config_path()
    if path.exists():
        settings |= parse_router_settings(path.read_text(encoding="utf-8"))
        settings["hostname"] = default_hostname()

    with db.connection(BIRD_DB_PATH) as conn:
        global_cfg = db.fetch_one_on(conn, "SELECT * FROM global_cfg WHERE id = 1")
        if global_cfg is not None:
            settings["router_id"] = str(global_cfg["router_id"])
            settings["hostname"] = str(global_cfg["hostname"] or default_hostname())

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
                "iface_name": str(device["iface_name"]),
            }
        else:
            settings["device"]["iface_name"] = default_iface_name()

        direct = db.fetch_one_on(conn, "SELECT * FROM proto_direct ORDER BY id LIMIT 1")
        if direct is not None:
            settings["direct"] = {
                "enabled": bool(direct["enabled"]),
                "iface_name": str(direct["iface_name"]),
            }
        else:
            settings["direct"]["iface_name"] = default_iface_name()
    return settings


def normalize_global_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate GUI payload for BIRD global settings."""
    kernel = payload.get("kernel") if isinstance(payload.get("kernel"), dict) else payload
    device = payload.get("device") if isinstance(payload.get("device"), dict) else payload
    direct = payload.get("direct") if isinstance(payload.get("direct"), dict) else payload
    return {
        "router_id": router_id_setting(payload.get("router_id")),
        "hostname": hostname_setting(payload.get("hostname")),
        "log_syslog": bool_setting(payload.get("log_syslog", True)),
        "kernel": {
            "enabled": bool_setting(kernel.get("kernel_enabled", kernel.get("enabled", True))),
            "route_table": int_setting(kernel.get("kernel_route_table", kernel.get("route_table")), default=254, minimum=1, maximum=4294967295, field="route_table"),
            "learn": "all" if str(kernel.get("kernel_learn", kernel.get("learn", ""))).strip().lower() == "all" else None,
            "channel_family": channel_family_setting(kernel.get("kernel_channel_family", kernel.get("channel_family"))),
            "channel_table_name": optional_text(kernel.get("kernel_channel_table_name", kernel.get("channel_table_name"))) or BIRD_DEFAULT_CHANNEL_TABLE_NAME,
            "import_policy": import_export_setting(kernel.get("kernel_import_policy", kernel.get("import_policy")), field="import_policy", default="all"),
            "export_policy": import_export_setting(kernel.get("kernel_export_policy", kernel.get("export_policy")), field="export_policy", default="none"),
            "metric": int_setting(kernel.get("kernel_metric", kernel.get("metric")), default=32, minimum=0, maximum=4294967295, field="metric"),
            "scan_time_secs": int_setting(kernel.get("kernel_scan_time_secs", kernel.get("scan_time_secs")), default=10, minimum=1, maximum=86400, field="scan_time_secs"),
            "persist": bool_setting(kernel.get("kernel_persist", kernel.get("persist", True))),
        },
        "device": {
            "enabled": bool_setting(device.get("device_enabled", device.get("enabled", True))),
            "scan_time_secs": int_setting(device.get("device_scan_time_secs", device.get("scan_time_secs")), default=10, minimum=1, maximum=86400, field="device_scan_time_secs"),
            "iface_name": iface_name_setting(device.get("device_iface_name", device.get("iface_name"))),
        },
        "direct": {
            "enabled": bool_setting(direct.get("direct_enabled", direct.get("enabled", True))),
            "iface_name": iface_name_setting(direct.get("direct_iface_name", direct.get("iface_name"))),
        },
    }


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
    ensure_bird_db()
    with db.transaction(BIRD_DB_PATH) as conn:
        updated = db.execute_on(
            conn,
            """
            UPDATE global_cfg
               SET router_id = ?, hostname = ?
             WHERE id = 1
            """,
            (settings["router_id"], settings["hostname"]),
        ).rowcount
        if updated == 0:
            db.execute_on(
                conn,
                "INSERT INTO global_cfg (id, router_id, hostname) VALUES (1, ?, ?)",
                (settings["router_id"], settings["hostname"]),
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


def default_rip_settings() -> dict[str, Any]:
    """Return default BIRD RIP protocol settings."""
    return {
        "enabled": False,
        "version": "2",
        "mode": "multicast",
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
    ensure_bird_db()
    settings = default_rip_settings()
    with db.connection(BIRD_DB_PATH) as conn:
        row = db.fetch_one_on(conn, "SELECT * FROM proto_rip ORDER BY id LIMIT 1")
    if row is None:
        return settings
    return {
        "enabled": bool(row["enabled"]),
        "version": str(row["version"]),
        "mode": str(row["mode"]),
        "multicast_addr": str(row["multicast_addr"]),
        "passive": bool(row["passive"]),
        "port": int(row["port"]),
        "update_time_secs": int(row["update_time_secs"]),
        "timeout_time_secs": int(row["timeout_time_secs"]),
        "garbage_time_secs": int(row["garbage_time_secs"]),
        "authentication": str(row["authentication"]),
        "password": str(row["password"] or ""),
    }


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
    default_addr = "ff02::9" if version == "ng" else "224.0.0.9"
    default_port = 521 if version == "ng" else 520
    multicast_addr = ip_address_setting(payload.get("multicast_addr") or default_addr, field="multicast_addr")
    port = int_setting(payload.get("port"), default=default_port, minimum=1, maximum=65535, field="port")
    password = optional_text(payload.get("password")) or ""
    if version == "ng":
        mode = "multicast"
        multicast_addr = "ff02::9"
        port = 521
    elif multicast_addr != "224.0.0.9" or port != 520:
        raise HTTPException(status_code=400, detail="RIP version 1 and 2 must use multicast address 224.0.0.9 and port 520.")
    if authentication != "none" and not password:
        raise HTTPException(status_code=400, detail="password is required when authentication is enabled.")
    if authentication == "none":
        password = ""
    return {
        "enabled": bool_setting(payload.get("enabled", True)),
        "version": version,
        "mode": mode,
        "multicast_addr": multicast_addr,
        "passive": bool_setting(payload.get("passive", False)),
        "port": port,
        "update_time_secs": int_setting(payload.get("update_time_secs"), default=30, minimum=1, maximum=86400, field="update_time_secs"),
        "timeout_time_secs": int_setting(payload.get("timeout_time_secs"), default=180, minimum=1, maximum=86400, field="timeout_time_secs"),
        "garbage_time_secs": int_setting(payload.get("garbage_time_secs"), default=120, minimum=1, maximum=86400, field="garbage_time_secs"),
        "authentication": authentication,
        "password": password,
    }


def save_rip_settings_to_db(settings: dict[str, Any]) -> None:
    """Persist BIRD RIP settings to bird.db."""
    ensure_bird_db()
    with db.transaction(BIRD_DB_PATH) as conn:
        existing = db.fetch_one_on(conn, "SELECT id FROM proto_rip ORDER BY id LIMIT 1")
        values = (
            settings["version"], settings["mode"], settings["multicast_addr"], 1 if settings["passive"] else 0,
            settings["port"], settings["update_time_secs"], settings["timeout_time_secs"], settings["garbage_time_secs"],
            settings["authentication"], settings["password"] or None, 1 if settings["enabled"] else 0,
        )
        if existing is None:
            db.execute_on(
                conn,
                """
                INSERT INTO proto_rip (
                    version, mode, multicast_addr, passive, port, update_time_secs,
                    timeout_time_secs, garbage_time_secs, authentication, password, enabled
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            return
        db.execute_on(
            conn,
            """
            UPDATE proto_rip
               SET version = ?, mode = ?, multicast_addr = ?, passive = ?, port = ?,
                   update_time_secs = ?, timeout_time_secs = ?, garbage_time_secs = ?,
                   authentication = ?, password = ?, enabled = ?
             WHERE id = ?
            """,
            (*values, int(existing["id"])),
        )


def channel_block(settings: dict[str, Any]) -> str:
    """Render one BIRD channel block."""
    families = ("ipv4", "ipv6") if settings["channel_family"] == "ipv4/ipv6" else (settings["channel_family"],)
    table_line = f"    table {settings['channel_table_name']};\n" if settings.get("channel_table_name") else ""
    return "".join(
        (
            f"  {family} {{\n"
            f"{table_line}"
            f"    import {settings['import_policy']};\n"
            f"    export {settings['export_policy']};\n"
            "  };\n"
        )
        for family in families
    )


def render_rip_config(settings: dict[str, Any]) -> str:
    """Render the managed BIRD RIP protocol block."""
    if not settings["enabled"]:
        return ""
    version_line = "  version 2;" if settings["version"] == "2" else "  version 1;" if settings["version"] == "1" else "  ipv6;"
    passive_line = "    passive yes;" if settings["passive"] else "    passive no;"
    auth_lines = ""
    if settings["authentication"] != "none":
        auth_lines = (
            f"    authentication {settings['authentication']};\n"
            f"    password \"{settings['password']}\";\n"
        )
    return (
        "protocol rip {\n"
        f"{version_line}\n"
        f"  port {settings['port']};\n"
        f"  update time {settings['update_time_secs']};\n"
        f"  timeout time {settings['timeout_time_secs']};\n"
        f"  garbage time {settings['garbage_time_secs']};\n"
        "  interface \"*\" {\n"
        f"    mode {settings['mode']};\n"
        f"    multicast address {settings['multicast_addr']};\n"
        f"{passive_line}\n"
        f"{auth_lines}"
        "  };\n"
        "}"
    )


def render_global_config(settings: dict[str, Any], rip_settings: dict[str, Any] | None = None) -> str:
    """Render a managed BIRD global configuration."""
    log_target = "all" if settings["log_syslog"] else "off"
    blocks = [
        "# Managed by ArmFirewall Network / Routing Protocols.",
        f"router id {settings['router_id']};",
        f"hostname \"{settings['hostname']}\";",
        f"log syslog {log_target};",
        "",
    ]

    device = settings["device"]
    if device["enabled"] and device["iface_name"]:
        blocks.extend([
            "protocol device {",
            f"  scan time {device['scan_time_secs']};",
            f"  interface \"{device['iface_name']}\";",
            "  ipv4;",
            "  ipv6;",
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

    kernel = settings["kernel"]
    if kernel["enabled"]:
        learn_line = "  learn all;\n" if kernel["learn"] == "all" else ""
        persist_line = "  persist;\n" if kernel["persist"] else ""
        blocks.append(
            "protocol kernel {\n"
            f"  kernel table {kernel['route_table']};\n"
            f"{learn_line}"
            f"{persist_line}"
            f"  metric {kernel['metric']};\n"
            f"  scan time {kernel['scan_time_secs']};\n"
            f"{channel_block(kernel)}"
            "}"
        )
    rip_block = render_rip_config(rip_settings or default_rip_settings())
    if rip_block:
        blocks.extend(["", rip_block])
    return "\n".join(blocks).rstrip() + "\n"


def get_global_settings() -> dict[str, Any]:
    """Return current BIRD global daemon settings and status."""
    settings = settings_from_db()
    path = bird_config_path()
    return {
        "service": bird_status(),
        "bird_version": bird_version(),
        "config_path": str(path),
        "exists": path.exists(),
        "settings": settings,
        "routing_tables": routing_tables(),
        "interfaces": interfaces(),
        "rendered_config": render_global_config(settings, rip_settings_from_db()),
    }


def save_global_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist BIRD global daemon settings to the host configuration file."""
    settings = normalize_global_settings(payload)
    save_settings_to_db(settings)
    path = bird_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_path = path.with_suffix(path.suffix + ".armfw.bak")
        shutil.copy2(path, backup_path)
    path.write_text(render_global_config(settings, rip_settings_from_db()), encoding="utf-8")
    return get_global_settings() | {"saved": True}


def get_rip_settings() -> dict[str, Any]:
    """Return current BIRD RIP protocol settings."""
    settings = rip_settings_from_db()
    return {
        "service": bird_status(),
        "settings": settings,
        "rendered_config": render_rip_config(settings),
    }


def save_rip_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist BIRD RIP protocol settings and rewrite bird.conf."""
    settings = normalize_rip_settings(payload)
    save_rip_settings_to_db(settings)
    global_settings = settings_from_db()
    path = bird_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_path = path.with_suffix(path.suffix + ".armfw.bak")
        shutil.copy2(path, backup_path)
    path.write_text(render_global_config(global_settings, settings), encoding="utf-8")
    return get_rip_settings() | {"saved": True}


def read_bird_logs(*, max_lines: int = 300) -> dict[str, Any]:
    """Return recent BIRD supervisord stdout log lines."""
    path = BIRD_LOG_PATH
    if not path.exists():
        return {"path": str(path), "exists": False, "lines": []}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {
        "path": str(path),
        "exists": True,
        "lines": lines[-max_lines:],
    }
