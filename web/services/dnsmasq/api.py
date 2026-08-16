from __future__ import annotations

import ipaddress
import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from core import db
from core import iface as iface_module
from core.constants import DNSMASQ_DB_PATH, ROOT_DIR, WORK_REQUEST_DB_PATH
from web.workrequests.api import list_work_requests
from web.services.api import service_status_by_name


DNSMASQ_CONF = ROOT_DIR / "conf" / "dnsmasq.conf"

DOMAIN_LABEL_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
BOOL_DEFAULTS = {
    "expand_hosts": True,
    "domain_needed": True,
    "bogus_priv": True,
    "dhcp_authoritative": False,
}
ALL_INTERFACES_TOKEN = "__all__"
INTERFACE_CONFIG_PREFIX = "# armfirewall-interface-config="


def default_config() -> dict[str, Any]:
    """Return default dnsmasq settings used by ArmFirewall."""
    return {
        "dns_enabled": False,
        "dhcp_enabled": False,
        "listen_interfaces": [],
        "local_domain": "armfirewall.local",
        "upstream_dns_servers": ["1.1.1.1", "8.8.8.8"],
        "domain_upstreams": [],
        "interface_configs": [],
        "pihole_upstream_enabled": False,
        "dhcp_range_start": "",
        "dhcp_range_end": "",
        "lease_time": "12h",
        "cache_size": 1000,
        "expand_hosts": BOOL_DEFAULTS["expand_hosts"],
        "domain_needed": BOOL_DEFAULTS["domain_needed"],
        "bogus_priv": BOOL_DEFAULTS["bogus_priv"],
        "dhcp_authoritative": BOOL_DEFAULTS["dhcp_authoritative"],
        "ipv6_ra_enabled": False,
        "ipv6_ra_names": True,
        "ipv6_ra_lifetime": "4h",
        "extra_options": "",
    }


def default_interface_config(iface_name: str) -> dict[str, Any]:
    """Return default DNS and DHCP settings for one interface."""
    return {
        "iface": iface_name,
        "dns_enabled": False,
        "local_domain": "armfirewall.local",
        "upstream_dns_servers": ["1.1.1.1", "8.8.8.8"],
        "domain_upstreams": [],
        "pihole_upstream_enabled": False,
        "cache_size": 1000,
        "expand_hosts": BOOL_DEFAULTS["expand_hosts"],
        "domain_needed": BOOL_DEFAULTS["domain_needed"],
        "bogus_priv": BOOL_DEFAULTS["bogus_priv"],
        "dhcp_enabled": False,
        "dhcp_range_start": "",
        "dhcp_range_end": "",
        "lease_time": "12h",
        "dhcp_authoritative": BOOL_DEFAULTS["dhcp_authoritative"],
        "ipv6_ra_enabled": False,
        "ipv6_ra_names": True,
        "ipv6_ra_lifetime": "4h",
    }


def interface_config_from_global(iface_name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Build one interface config from legacy global settings."""
    item = default_interface_config(iface_name)
    for key in item:
        if key != "iface" and key in config:
            item[key] = config[key]
    return item


def read_config_lines() -> list[str]:
    """Read dnsmasq.conf lines when the file exists."""
    if not DNSMASQ_CONF.exists():
        return []
    return DNSMASQ_CONF.read_text(encoding="utf-8").splitlines()


def parse_bool_line(lines: list[str], directive: str, default: bool = False) -> bool:
    """Return whether a boolean dnsmasq directive is present."""
    return any(line.strip() == directive for line in lines) or default and not lines


def split_csv(value: str) -> list[str]:
    """Split comma-separated dnsmasq values."""
    return [part.strip() for part in value.split(",") if part.strip()]


def split_server_tokens(value: str) -> list[str]:
    """Split server lists from GUI text fields."""
    return [part.strip() for part in re.split(r"[\s,]+", value) if part.strip()]


def parse_domain_server(value: str) -> tuple[str, str] | None:
    """Parse a dnsmasq domain-specific server directive."""
    if not value.startswith("/"):
        return None
    parts = value[1:].split("/", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        return None
    return parts[0].strip(), parts[1].strip()


def parse_dnsmasq_config(lines: list[str]) -> dict[str, Any]:
    """Parse ArmFirewall-managed dnsmasq settings from dnsmasq.conf."""
    config = default_config()
    known: set[int] = set()
    servers: list[str] = []
    domain_servers: dict[str, list[str]] = {}
    interfaces: list[str] = []
    interface_configs: list[dict[str, Any]] = []
    extras: list[str] = []

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line.startswith(INTERFACE_CONFIG_PREFIX):
            try:
                parsed = json.loads(line.removeprefix(INTERFACE_CONFIG_PREFIX).strip())
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and parsed.get("iface"):
                interface_configs.append(parsed)
            known.add(index)
            continue
        if line.startswith("# armfirewall-listen-all-interfaces="):
            if line.split("=", 1)[1].strip() == "1":
                interfaces = [ALL_INTERFACES_TOKEN]
            known.add(index)
            continue
        if line.startswith("# armfirewall-pihole-upstream="):
            config["pihole_upstream_enabled"] = line.split("=", 1)[1].strip() == "1"
            known.add(index)
            continue
        if not line or line.startswith("#"):
            known.add(index)
            continue
        if line == "bind-interfaces":
            known.add(index)
            continue
        if line == "expand-hosts":
            config["expand_hosts"] = True
            known.add(index)
            continue
        if line == "domain-needed":
            config["domain_needed"] = True
            known.add(index)
            continue
        if line == "bogus-priv":
            config["bogus_priv"] = True
            known.add(index)
            continue
        if line == "dhcp-authoritative":
            config["dhcp_authoritative"] = True
            known.add(index)
            continue
        if line.startswith("port="):
            config["dns_enabled"] = line.split("=", 1)[1].strip() != "0"
            known.add(index)
            continue
        if line.startswith("interface="):
            interfaces.append(line.split("=", 1)[1].strip())
            known.add(index)
            continue
        if line.startswith("domain="):
            config["local_domain"] = line.split("=", 1)[1].strip()
            known.add(index)
            continue
        if line.startswith("local=/"):
            known.add(index)
            continue
        if line.startswith("server="):
            server_value = line.split("=", 1)[1].strip()
            domain_server = parse_domain_server(server_value)
            if domain_server:
                domain, upstream = domain_server
                domain_servers.setdefault(domain, []).append(upstream)
            else:
                servers.append(server_value)
            known.add(index)
            continue
        if line.startswith("cache-size="):
            config["cache_size"] = line.split("=", 1)[1].strip()
            known.add(index)
            continue
        if line.startswith("dhcp-range="):
            parts = split_csv(line.split("=", 1)[1])
            config["dhcp_enabled"] = True
            config["dhcp_range_start"] = parts[0] if len(parts) > 0 else ""
            config["dhcp_range_end"] = parts[1] if len(parts) > 1 else ""
            config["lease_time"] = parts[2] if len(parts) > 2 else config["lease_time"]
            known.add(index)
            continue

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if index not in known and line:
            extras.append(raw_line)

    if interfaces:
        config["listen_interfaces"] = interfaces
    if servers:
        config["upstream_dns_servers"] = servers
    if domain_servers:
        config["domain_upstreams"] = [
            {"domain": domain, "upstreams": upstreams}
            for domain, upstreams in sorted(domain_servers.items())
        ]
    if interface_configs:
        config["interface_configs"] = interface_configs
    elif interfaces:
        config["interface_configs"] = [interface_config_from_global(iface_name, config) for iface_name in interfaces]
    config["extra_options"] = "\n".join(extras)
    return config


def json_array(value: Any) -> list[Any]:
    """Return a JSON array value as a Python list."""
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def bool_from_db(value: Any) -> bool:
    """Convert an SQLite integer boolean to bool."""
    return int(value or 0) == 1


def ensure_dnsmasq_schema(conn: db.Connection) -> None:
    """Add global DNS columns when an older dnsmasq.db is found."""
    columns = {row["name"] for row in db.execute_on(conn, "PRAGMA table_info(dnsmasq_settings)").fetchall()}
    column_defs = {
        "dns_enabled": "INTEGER NOT NULL DEFAULT 0 CHECK (dns_enabled IN (0, 1))",
        "local_domain": "TEXT NOT NULL DEFAULT 'armfirewall.local'",
        "upstream_dns_servers_json": "TEXT NOT NULL DEFAULT '[\"1.1.1.1\",\"8.8.8.8\"]'",
        "pihole_upstream_enabled": "INTEGER NOT NULL DEFAULT 0 CHECK (pihole_upstream_enabled IN (0, 1))",
        "cache_size": "INTEGER NOT NULL DEFAULT 1000 CHECK (cache_size BETWEEN 0 AND 1000000)",
        "expand_hosts": "INTEGER NOT NULL DEFAULT 1 CHECK (expand_hosts IN (0, 1))",
        "domain_needed": "INTEGER NOT NULL DEFAULT 1 CHECK (domain_needed IN (0, 1))",
        "bogus_priv": "INTEGER NOT NULL DEFAULT 1 CHECK (bogus_priv IN (0, 1))",
    }
    for name, definition in column_defs.items():
        if name not in columns:
            db.execute_on(conn, f"ALTER TABLE dnsmasq_settings ADD COLUMN {name} {definition}")
    interface_columns = {
        row["name"]
        for row in db.execute_on(
            conn, "PRAGMA table_info(dnsmasq_interface_configs)"
        ).fetchall()
    }
    interface_column_defs = {
        "ipv6_ra_enabled": "INTEGER NOT NULL DEFAULT 0 CHECK (ipv6_ra_enabled IN (0, 1))",
        "ipv6_ra_names": "INTEGER NOT NULL DEFAULT 1 CHECK (ipv6_ra_names IN (0, 1))",
        "ipv6_ra_lifetime": "TEXT NOT NULL DEFAULT '4h'",
    }
    for name, definition in interface_column_defs.items():
        if name not in interface_columns:
            db.execute_on(
                conn,
                f"ALTER TABLE dnsmasq_interface_configs ADD COLUMN {name} {definition}",
            )
    db.execute_on(
        conn,
        """
        CREATE TABLE IF NOT EXISTS dnsmasq_global_domain_upstreams (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             domain TEXT NOT NULL UNIQUE,
             upstream_dns_servers_json TEXT NOT NULL,
             created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
             updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    db.execute_on(
        conn,
        """
        CREATE INDEX IF NOT EXISTS idx_dnsmasq_global_domain_upstreams_domain
        ON dnsmasq_global_domain_upstreams (domain)
        """,
    )


def load_config_from_db() -> dict[str, Any] | None:
    """Load the pending or applied Dnsmasq configuration from SQLite."""
    if not DNSMASQ_DB_PATH.exists():
        return None

    with db.connection(DNSMASQ_DB_PATH) as conn:
        ensure_dnsmasq_schema(conn)
        settings = db.fetch_one_on(
            conn,
            """
            SELECT dns_enabled, local_domain, upstream_dns_servers_json,
                   pihole_upstream_enabled, cache_size, expand_hosts,
                   domain_needed, bogus_priv, extra_options
            FROM dnsmasq_settings
            WHERE id = 1
            """,
        )
        global_upstream_rows = db.execute_on(
            conn,
            """
            SELECT domain, upstream_dns_servers_json
            FROM dnsmasq_global_domain_upstreams
            ORDER BY id
            """,
        ).fetchall()
        rows = db.execute_on(
            conn,
            """
            SELECT id, iface, dns_enabled, local_domain, upstream_dns_servers_json,
                   pihole_upstream_enabled, cache_size, expand_hosts, domain_needed,
                   bogus_priv, dhcp_enabled, dhcp_range_start, dhcp_range_end,
                   lease_time, dhcp_authoritative, ipv6_ra_enabled,
                   ipv6_ra_names, ipv6_ra_lifetime
            FROM dnsmasq_interface_configs
            WHERE enabled = 1
            ORDER BY id
            """,
        ).fetchall()

        if not rows and settings is None:
            return None

        interface_configs: list[dict[str, Any]] = []
        for row in rows:
            upstream_rows = db.execute_on(
                conn,
                """
                SELECT domain, upstream_dns_servers_json
                FROM dnsmasq_domain_upstreams
                WHERE interface_config_id = ?
                ORDER BY id
                """,
                (row["id"],),
            ).fetchall()
            interface_configs.append(
                {
                    "iface": row["iface"],
                    "dns_enabled": bool_from_db(row["dns_enabled"]),
                    "local_domain": row["local_domain"],
                    "upstream_dns_servers": [str(item) for item in json_array(row["upstream_dns_servers_json"])],
                    "domain_upstreams": [
                        {
                            "domain": upstream["domain"],
                            "upstreams": [str(item) for item in json_array(upstream["upstream_dns_servers_json"])],
                        }
                        for upstream in upstream_rows
                    ],
                    "pihole_upstream_enabled": bool_from_db(row["pihole_upstream_enabled"]),
                    "cache_size": int(row["cache_size"]),
                    "expand_hosts": bool_from_db(row["expand_hosts"]),
                    "domain_needed": bool_from_db(row["domain_needed"]),
                    "bogus_priv": bool_from_db(row["bogus_priv"]),
                    "dhcp_enabled": bool_from_db(row["dhcp_enabled"]),
                    "dhcp_range_start": row["dhcp_range_start"],
                    "dhcp_range_end": row["dhcp_range_end"],
                    "lease_time": row["lease_time"],
                    "dhcp_authoritative": bool_from_db(row["dhcp_authoritative"]),
                    "ipv6_ra_enabled": bool_from_db(row["ipv6_ra_enabled"]),
                    "ipv6_ra_names": bool_from_db(row["ipv6_ra_names"]),
                    "ipv6_ra_lifetime": row["ipv6_ra_lifetime"],
                }
            )

    config = default_config()
    if settings:
        config.update(
            {
                "dns_enabled": bool_from_db(settings["dns_enabled"]),
                "local_domain": settings["local_domain"],
                "upstream_dns_servers": [str(item) for item in json_array(settings["upstream_dns_servers_json"])],
                "domain_upstreams": [
                    {
                        "domain": row["domain"],
                        "upstreams": [str(item) for item in json_array(row["upstream_dns_servers_json"])],
                    }
                    for row in global_upstream_rows
                ],
                "pihole_upstream_enabled": bool_from_db(settings["pihole_upstream_enabled"]),
                "cache_size": int(settings["cache_size"]),
                "expand_hosts": bool_from_db(settings["expand_hosts"]),
                "domain_needed": bool_from_db(settings["domain_needed"]),
                "bogus_priv": bool_from_db(settings["bogus_priv"]),
                "extra_options": settings["extra_options"],
            }
        )
    legacy_dns = next((item for item in interface_configs if item["dns_enabled"]), None)
    if legacy_dns and not config["dns_enabled"]:
        config.update(
            {
                "dns_enabled": legacy_dns["dns_enabled"],
                "local_domain": legacy_dns["local_domain"],
                "upstream_dns_servers": legacy_dns["upstream_dns_servers"],
                "domain_upstreams": legacy_dns["domain_upstreams"],
                "pihole_upstream_enabled": legacy_dns["pihole_upstream_enabled"],
                "cache_size": legacy_dns["cache_size"],
                "expand_hosts": legacy_dns["expand_hosts"],
                "domain_needed": legacy_dns["domain_needed"],
                "bogus_priv": legacy_dns["bogus_priv"],
            }
        )
    if not interface_configs:
        return config

    config.update(
        {
            "dhcp_enabled": any(item["dhcp_enabled"] for item in interface_configs),
            "listen_interfaces": [item["iface"] for item in interface_configs],
            "interface_configs": interface_configs,
        }
    )
    return config


def save_config_to_db(config: dict[str, Any]) -> int:
    """Persist normalized Dnsmasq settings and return the work request id."""
    request_uid = str(uuid.uuid4())
    payload = {"config_db": str(DNSMASQ_DB_PATH), "config_path": str(DNSMASQ_CONF)}

    with db.transaction(DNSMASQ_DB_PATH) as conn:
        ensure_dnsmasq_schema(conn)
        db.execute_on(
            conn,
            """
            INSERT INTO dnsmasq_settings (
                id, dns_enabled, local_domain, upstream_dns_servers_json,
                pihole_upstream_enabled, cache_size, expand_hosts, domain_needed,
                bogus_priv, extra_options, pending_apply, updated_at
            )
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                dns_enabled = excluded.dns_enabled,
                local_domain = excluded.local_domain,
                upstream_dns_servers_json = excluded.upstream_dns_servers_json,
                pihole_upstream_enabled = excluded.pihole_upstream_enabled,
                cache_size = excluded.cache_size,
                expand_hosts = excluded.expand_hosts,
                domain_needed = excluded.domain_needed,
                bogus_priv = excluded.bogus_priv,
                extra_options = excluded.extra_options,
                pending_apply = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                int(config["dns_enabled"]),
                config["local_domain"],
                json.dumps(config["upstream_dns_servers"], sort_keys=True),
                int(config["pihole_upstream_enabled"]),
                int(config["cache_size"]),
                int(config["expand_hosts"]),
                int(config["domain_needed"]),
                int(config["bogus_priv"]),
                config["extra_options"],
            ),
        )
        db.execute_on(conn, "DELETE FROM dnsmasq_global_domain_upstreams")
        for domain_item in config.get("domain_upstreams", []):
            db.execute_on(
                conn,
                """
                INSERT INTO dnsmasq_global_domain_upstreams (domain, upstream_dns_servers_json)
                VALUES (?, ?)
                """,
                (domain_item["domain"], json.dumps(domain_item["upstreams"], sort_keys=True)),
            )
        db.execute_on(conn, "DELETE FROM dnsmasq_interface_configs")

        for item in config.get("interface_configs", []):
            cursor = db.execute_on(
                conn,
                """
                INSERT INTO dnsmasq_interface_configs (
                    iface, dns_enabled, local_domain, upstream_dns_servers_json,
                    pihole_upstream_enabled, cache_size, expand_hosts, domain_needed,
                    bogus_priv, dhcp_enabled, dhcp_range_start, dhcp_range_end,
                    lease_time, dhcp_authoritative, ipv6_ra_enabled,
                    ipv6_ra_names, ipv6_ra_lifetime, enabled
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    item["iface"],
                    int(item["dns_enabled"]),
                    item["local_domain"],
                    json.dumps(item["upstream_dns_servers"], sort_keys=True),
                    int(item["pihole_upstream_enabled"]),
                    int(item["cache_size"]),
                    int(item["expand_hosts"]),
                    int(item["domain_needed"]),
                    int(item["bogus_priv"]),
                    int(item["dhcp_enabled"]),
                    item["dhcp_range_start"],
                    item["dhcp_range_end"],
                    item["lease_time"],
                    int(item["dhcp_authoritative"]),
                    int(item["ipv6_ra_enabled"]),
                    int(item["ipv6_ra_names"]),
                    item["ipv6_ra_lifetime"],
                ),
            )
            interface_config_id = int(cursor.lastrowid)
            for domain_item in item.get("domain_upstreams", []):
                db.execute_on(
                    conn,
                    """
                    INSERT INTO dnsmasq_domain_upstreams (
                        interface_config_id, domain, upstream_dns_servers_json
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        interface_config_id,
                        domain_item["domain"],
                        json.dumps(domain_item["upstreams"], sort_keys=True),
                    ),
                )

    with db.transaction(WORK_REQUEST_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            INSERT INTO work_requests (
                request_uid, source, category_name, action_name,
                target_rule_id, priority, status, payload_json
            )
            VALUES (?, 'gui', 'SERVICE_MANAGEMENT.DNSMASQ_CONFIG', 'apply', NULL, 70, 'queue', ?)
            """,
            (request_uid, json.dumps(payload, sort_keys=True)),
        )
        work_request_id = int(cursor.lastrowid)
        db.execute_on(
            conn,
            """
            INSERT INTO work_request_events (work_request_id, event_type, message)
            VALUES (?, 'queue', 'Queued Dnsmasq configuration apply.')
            """,
            (work_request_id,),
        )

    with db.transaction(DNSMASQ_DB_PATH) as conn:
        db.execute_on(
            conn,
            """
            UPDATE dnsmasq_settings
            SET last_work_request_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (work_request_id,),
        )

    return work_request_id


def list_interfaces() -> list[dict[str, Any]]:
    """Return available interfaces for dnsmasq binding."""
    try:
        return iface_module.get_interfaces().get("interfaces", [])
    except (FileNotFoundError, db.DatabaseError):
        return []


def dnsmasq_version() -> str:
    """Return the installed dnsmasq version when available."""
    dnsmasq = shutil.which("dnsmasq")
    if not dnsmasq:
        return "not installed"
    try:
        result = subprocess.run(
            [dnsmasq, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    output = (result.stdout or result.stderr).strip().splitlines()
    if not output:
        return "unknown"
    match = re.search(r"version\s+([^\s,]+)", output[0], re.IGNORECASE)
    return match.group(1) if match else output[0]


def dnsmasq_status() -> dict[str, Any]:
    """Return persisted dnsmasq service status."""
    status = service_status_by_name("dnsmasq")
    status["version"] = dnsmasq_version()
    return status


def get_dnsmasq_work_requests(limit: int = 50) -> dict[str, Any]:
    """Return recent Dnsmasq configuration and service control work requests."""
    return list_work_requests(
        limit=limit,
        category_names=("SERVICE_MANAGEMENT.DNSMASQ_CONFIG", "SERVICE_MANAGEMENT.SERVICE_CONTROL"),
        service_name="dnsmasq",
        service_name_categories=("SERVICE_MANAGEMENT.SERVICE_CONTROL",),
    )


def get_dnsmasq_config() -> dict[str, Any]:
    """Return dnsmasq configuration, interfaces, and service state."""
    config = load_config_from_db()
    if config is None:
        config = parse_dnsmasq_config(read_config_lines())
    return {
        "config": config,
        "interfaces": list_interfaces(),
        "service": dnsmasq_status(),
        "summary": {
            "config_path": str(DNSMASQ_CONF),
            "config_db": str(DNSMASQ_DB_PATH),
            "exists": DNSMASQ_CONF.exists(),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def validate_ip(value: str, field_name: str) -> str:
    """Validate and normalize one IP address."""
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be a valid IP address.") from exc


def validate_optional_ip(value: Any, field_name: str) -> str:
    """Validate an optional IP address field."""
    text = str(value or "").strip()
    return validate_ip(text, field_name) if text else ""


def validate_dns_domain(value: Any, field_name: str) -> str:
    """Validate one DNS domain field."""
    domain = str(value or "armfirewall.local").strip().strip(".")
    labels = domain.split(".")
    if (
        not domain
        or len(domain) > 253
        or ".." in domain
        or len(labels) < 2
        or all(label.isdigit() for label in labels)
        or any(not DOMAIN_LABEL_RE.match(label) for label in labels)
    ):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a valid DNS domain.")
    return domain


def validate_domain(value: Any) -> str:
    """Validate the local DNS domain."""
    return validate_dns_domain(value, "local_domain")


def validate_interfaces(values: Any) -> list[str]:
    """Validate requested listen interfaces."""
    requested = [str(item).strip() for item in values or [] if str(item).strip()]
    if ALL_INTERFACES_TOKEN in requested:
        return [ALL_INTERFACES_TOKEN]
    available = {str(item.get("name")) for item in list_interfaces()}
    if available:
        invalid = sorted(set(requested) - available)
        if invalid:
            raise HTTPException(status_code=400, detail=f"Unknown interface(s): {', '.join(invalid)}")
    return requested


def normalize_upstream_list(value: Any, field_name: str) -> list[str]:
    """Validate a list or text block of upstream DNS servers."""
    if isinstance(value, str):
        raw_items = split_server_tokens(value)
    else:
        raw_items = [str(item).strip() for item in value or [] if str(item).strip()]
    return [validate_ip(item, field_name) for item in raw_items]


def validate_domain_upstreams(values: Any) -> list[dict[str, Any]]:
    """Validate domain-specific upstream DNS rules."""
    rules: dict[str, list[str]] = {}
    for item in values or []:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="domain_upstreams entries must be objects.")
        domain = validate_dns_domain(item.get("domain"), "domain_upstreams.domain")
        upstreams = normalize_upstream_list(item.get("upstreams"), "domain_upstreams.upstreams")
        if not upstreams:
            raise HTTPException(status_code=400, detail=f"At least one upstream is required for {domain}.")
        rules.setdefault(domain, [])
        for upstream in upstreams:
            if upstream not in rules[domain]:
                rules[domain].append(upstream)
    return [{"domain": domain, "upstreams": upstreams} for domain, upstreams in sorted(rules.items())]


def normalize_interface_config(item: dict[str, Any]) -> dict[str, Any]:
    """Validate one per-interface dnsmasq configuration."""
    iface_name = validate_interfaces([item.get("iface")])[0]
    config = default_interface_config(iface_name)
    config["dns_enabled"] = False
    config["upstream_dns_servers"] = []
    config["domain_upstreams"] = []
    config["dhcp_enabled"] = bool(item.get("dhcp_enabled"))
    config["dhcp_range_start"] = validate_optional_ip(item.get("dhcp_range_start"), f"{iface_name}.dhcp_range_start")
    config["dhcp_range_end"] = validate_optional_ip(item.get("dhcp_range_end"), f"{iface_name}.dhcp_range_end")
    config["lease_time"] = validate_lease_time(item.get("lease_time"))
    config["dhcp_authoritative"] = bool(item.get("dhcp_authoritative"))
    config["ipv6_ra_enabled"] = bool(item.get("ipv6_ra_enabled"))
    config["ipv6_ra_names"] = bool(item.get("ipv6_ra_names", True))
    config["ipv6_ra_lifetime"] = validate_lease_time(item.get("ipv6_ra_lifetime") or "4h")

    if config["ipv6_ra_enabled"]:
        if iface_name == ALL_INTERFACES_TOKEN:
            raise HTTPException(status_code=400, detail="IPv6 Router Advertisements require a specific interface.")
        interface = next(
            (item for item in list_interfaces() if item.get("name") == iface_name),
            None,
        )
        has_routable_ipv6 = interface and any(
            str(address.get("addr_family")) == "ipv6"
            and not str(address.get("addr", "")).lower().startswith("fe80:")
            and str(address.get("addr")) != "::1"
            for address in interface.get("addresses", [])
        )
        if not has_routable_ipv6:
            raise HTTPException(
                status_code=400,
                detail=(
                    "IPv6 Router Advertisements require an interface with a "
                    f"routable IPv6 prefix: {iface_name}."
                ),
            )

    if config["dhcp_enabled"] and (not config["dhcp_range_start"] or not config["dhcp_range_end"]):
        raise HTTPException(status_code=400, detail=f"DHCP range start and end are required for {iface_name}.")
    if config["dhcp_enabled"]:
        start = ipaddress.ip_address(config["dhcp_range_start"])
        end = ipaddress.ip_address(config["dhcp_range_end"])
        if start.version != end.version or int(start) > int(end):
            raise HTTPException(status_code=400, detail=f"DHCP range for {iface_name} must use one address family and start before end.")
    return config


def normalize_interface_configs(values: Any, fallback: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate per-interface DNS and DHCP settings."""
    if not values:
        configs = []
        for iface_name in fallback["listen_interfaces"]:
            if iface_name == ALL_INTERFACES_TOKEN:
                continue
            config = default_interface_config(iface_name)
            config["dhcp_enabled"] = bool(fallback.get("dhcp_enabled"))
            config["dhcp_range_start"] = fallback.get("dhcp_range_start", "")
            config["dhcp_range_end"] = fallback.get("dhcp_range_end", "")
            config["lease_time"] = fallback.get("lease_time", "12h")
            config["dhcp_authoritative"] = bool(fallback.get("dhcp_authoritative"))
            config["ipv6_ra_enabled"] = bool(fallback.get("ipv6_ra_enabled"))
            config["ipv6_ra_names"] = bool(fallback.get("ipv6_ra_names", True))
            config["ipv6_ra_lifetime"] = fallback.get("ipv6_ra_lifetime", "4h")
            configs.append(normalize_interface_config(config))
        return configs
    configs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="interface_configs entries must be objects.")
        config = normalize_interface_config(item)
        if config["iface"] in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate interface config: {config['iface']}.")
        seen.add(config["iface"])
        configs.append(config)
    return configs


def validate_lease_time(value: Any) -> str:
    """Validate a dnsmasq DHCP lease time token."""
    lease_time = str(value or "12h").strip()
    if not re.match(r"^\d+[smhdw]?$|^infinite$", lease_time):
        raise HTTPException(status_code=400, detail="lease_time must be like 12h, 30m, 3600, or infinite.")
    return lease_time


def validate_cache_size(value: Any) -> int:
    """Validate dnsmasq cache size."""
    try:
        cache_size = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="cache_size must be an integer.") from exc
    if cache_size < 0 or cache_size > 1000000:
        raise HTTPException(status_code=400, detail="cache_size must be between 0 and 1000000.")
    return cache_size


def normalize_extra_options(value: Any) -> str:
    """Normalize optional raw dnsmasq directives from the GUI."""
    lines = []
    for line in str(value or "").splitlines():
        item = line.strip()
        if item and item != "-":
            lines.append(item)
    return "\n".join(lines)


def normalize_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize dnsmasq GUI payload."""
    config = default_config()
    has_interface_configs = bool(payload.get("interface_configs"))
    config["dns_enabled"] = bool(payload.get("dns_enabled"))
    config["dhcp_enabled"] = bool(payload.get("dhcp_enabled"))
    config["listen_interfaces"] = validate_interfaces(payload.get("listen_interfaces"))
    config["local_domain"] = validate_domain(payload.get("local_domain"))
    config["upstream_dns_servers"] = normalize_upstream_list(payload.get("upstream_dns_servers"), "upstream_dns_servers")
    config["domain_upstreams"] = validate_domain_upstreams(payload.get("domain_upstreams"))
    config["pihole_upstream_enabled"] = bool(payload.get("pihole_upstream_enabled"))
    config["dhcp_range_start"] = validate_optional_ip(payload.get("dhcp_range_start"), "dhcp_range_start")
    config["dhcp_range_end"] = validate_optional_ip(payload.get("dhcp_range_end"), "dhcp_range_end")
    config["lease_time"] = validate_lease_time(payload.get("lease_time"))
    config["cache_size"] = validate_cache_size(payload.get("cache_size", config["cache_size"]))
    config["expand_hosts"] = bool(payload.get("expand_hosts"))
    config["domain_needed"] = bool(payload.get("domain_needed"))
    config["bogus_priv"] = bool(payload.get("bogus_priv"))
    config["dhcp_authoritative"] = bool(payload.get("dhcp_authoritative"))
    config["extra_options"] = normalize_extra_options(payload.get("extra_options"))

    if not config["listen_interfaces"] and not has_interface_configs:
        config["dns_enabled"] = False
        config["dhcp_enabled"] = False
        config["domain_upstreams"] = []
        config["interface_configs"] = []
        return config

    if has_interface_configs:
        config["interface_configs"] = normalize_interface_configs(payload.get("interface_configs"), config)
        config["listen_interfaces"] = [item["iface"] for item in config["interface_configs"]]
        config["dhcp_enabled"] = any(item["dhcp_enabled"] for item in config["interface_configs"])
        return config

    if config["dns_enabled"] and not config["pihole_upstream_enabled"] and not config["upstream_dns_servers"]:
        raise HTTPException(status_code=400, detail="At least one upstream DNS server is required when DNS is enabled.")
    if config["dhcp_enabled"] and (not config["dhcp_range_start"] or not config["dhcp_range_end"]):
        raise HTTPException(status_code=400, detail="DHCP range start and end are required when DHCP is enabled.")
    if config["dhcp_enabled"]:
        start = ipaddress.ip_address(config["dhcp_range_start"])
        end = ipaddress.ip_address(config["dhcp_range_end"])
        if start.version != end.version or int(start) > int(end):
            raise HTTPException(status_code=400, detail="DHCP range must use one address family and start before end.")

    config["interface_configs"] = normalize_interface_configs(payload.get("interface_configs"), config)
    return config


def render_config(config: dict[str, Any]) -> str:
    """Render normalized settings as dnsmasq.conf content."""
    interface_configs = config.get("interface_configs") or [
        interface_config_from_global(iface_name, config)
        for iface_name in config.get("listen_interfaces", [])
        if iface_name != ALL_INTERFACES_TOKEN
    ]
    has_listen_scope = bool(config.get("listen_interfaces"))
    dns_enabled = bool(config["dns_enabled"]) and has_listen_scope
    dhcp_enabled = any(item["dhcp_enabled"] for item in interface_configs) or bool(config["dhcp_enabled"])
    ipv6_ra_enabled = any(item["ipv6_ra_enabled"] for item in interface_configs)
    lines = [
        "# ArmFirewall managed dnsmasq configuration.",
        "# Generated from Services / Dnsmasq.",
        f"port={53 if dns_enabled else 0}",
        "bind-interfaces",
    ]

    if ipv6_ra_enabled:
        lines.append("enable-ra")

    if ALL_INTERFACES_TOKEN in config["listen_interfaces"]:
        lines.append("# armfirewall-listen-all-interfaces=1")
    else:
        lines.append("# armfirewall-listen-all-interfaces=0")
        for iface_name in config["listen_interfaces"]:
            lines.append(f"interface={iface_name}")

    rendered_domains: set[str] = set()
    rendered_locals: set[str] = set()
    rendered_servers: set[str] = set()
    rendered_directives: set[str] = set()
    rendered_ranges: set[str] = set()

    if dns_enabled:
        domain = config["local_domain"]
        lines.append(f"domain={domain}")
        lines.append(f"local=/{domain}/")
        lines.append(f"cache-size={config['cache_size']}")
        for enabled, directive in (
            (config["expand_hosts"], "expand-hosts"),
            (config["domain_needed"], "domain-needed"),
            (config["bogus_priv"], "bogus-priv"),
        ):
            if enabled:
                lines.append(directive)
        if not config["pihole_upstream_enabled"]:
            for server in config["upstream_dns_servers"]:
                lines.append(f"server={server}")
            for domain_item in config["domain_upstreams"]:
                for server in domain_item["upstreams"]:
                    lines.append(f"server=/{domain_item['domain']}/{server}")

    for item in interface_configs:
        if item["dhcp_enabled"]:
            range_line = (
                f"dhcp-range=tag:{item['iface']},"
                f"{item['dhcp_range_start']},{item['dhcp_range_end']},{item['lease_time']}"
            )
            if range_line not in rendered_ranges:
                lines.append(f"# DHCP scope for {item['iface']}")
                lines.append(range_line)
                rendered_ranges.add(range_line)
            if item["dhcp_authoritative"] and "dhcp-authoritative" not in rendered_directives:
                lines.append("dhcp-authoritative")
                rendered_directives.add("dhcp-authoritative")
        if item["ipv6_ra_enabled"]:
            options = ["ra-stateless"]
            if item["ipv6_ra_names"]:
                options.append("ra-names")
            lines.append(f"# IPv6 Router Advertisement for {item['iface']}")
            lines.append(
                f"dhcp-range=::1,constructor:{item['iface']},"
                f"{','.join(options)},{item['ipv6_ra_lifetime']}"
            )

    if config["extra_options"]:
        lines.append("")
        lines.append("# Extra options")
        lines.extend(line.rstrip() for line in config["extra_options"].splitlines() if line.strip() and line.strip() != "-")

    return "\n".join(lines).rstrip() + "\n"


def validate_dnsmasq_syntax(config_text: str) -> tuple[bool, str]:
    """Validate generated dnsmasq config when dnsmasq is installed."""
    dnsmasq = shutil.which("dnsmasq")
    if not dnsmasq:
        return True, "dnsmasq binary was not found; syntax validation skipped."

    tmp_path = DNSMASQ_CONF.with_suffix(".conf.check")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_text(config_text, encoding="utf-8")
    result = subprocess.run(
        [dnsmasq, "--test", f"--conf-file={tmp_path}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        match = re.search(r"line\s+(\d+)", output)
        if match:
            line_number = int(match.group(1))
            lines = config_text.splitlines()
            if 1 <= line_number <= len(lines):
                output = f"{output}: {lines[line_number - 1]}"
        return False, output or "dnsmasq syntax check failed."
    tmp_path.unlink(missing_ok=True)
    return result.returncode == 0, output or "dnsmasq syntax check completed."


def save_dnsmasq_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist dnsmasq settings and queue an apply work request."""
    config = normalize_config(payload)
    config_text = render_config(config)
    ok, message = validate_dnsmasq_syntax(config_text)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    work_request_id = save_config_to_db(config)
    return {
        "saved": True,
        "queued": True,
        "work_request_id": work_request_id,
        "message": "Dnsmasq configuration queued for apply.",
        "config": config,
        "summary": {
            "config_path": str(DNSMASQ_CONF),
            "config_db": str(DNSMASQ_DB_PATH),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def test_dnsmasq_config(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate either posted settings or the current dnsmasq.conf."""
    if payload:
        config_text = render_config(normalize_config(payload))
    else:
        config_text = DNSMASQ_CONF.read_text(encoding="utf-8") if DNSMASQ_CONF.exists() else render_config(default_config())

    ok, message = validate_dnsmasq_syntax(config_text)
    return {"ok": ok, "message": message}
