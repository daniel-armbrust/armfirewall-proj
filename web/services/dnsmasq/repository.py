"""SQLite persistence for DNSMasq settings and reservations."""
from __future__ import annotations
import json
from typing import Any
from core import db
from core.constants import DNSMASQ_DB_PATH, DNSMASQ_CONF_PATH, WORK_REQUEST_DB_PATH
from .configuration import default_config

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
        CREATE TABLE IF NOT EXISTS dnsmasq_static_leases (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             mac_address TEXT NOT NULL UNIQUE,
             ip_address TEXT NOT NULL UNIQUE,
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
        static_lease_rows = db.execute_on(
            conn,
            """
            SELECT id, mac_address, ip_address
            FROM dnsmasq_static_leases
            ORDER BY ip_address, mac_address
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
    config["static_leases"] = [
        {"id": int(row["id"]), "mac_address": row["mac_address"], "ip_address": row["ip_address"]}
        for row in static_lease_rows
    ]
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
    payload = {"config_db": str(DNSMASQ_DB_PATH), "config_path": str(DNSMASQ_CONF_PATH)}

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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
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
            VALUES (?, 'queue', 'Queued DNSMasq configuration apply.')
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

