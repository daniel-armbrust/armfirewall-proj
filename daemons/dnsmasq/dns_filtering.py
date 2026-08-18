"""Synchronize protected DNS rules with the configured filtering mode."""

from __future__ import annotations

from types import SimpleNamespace

from core import db
from core.constants import ADGUARD_HOME_DNS_PORT, DNSMASQ_DB_PATH, DNSMASQ_DNS_PORT
from daemons.fwrulesd.actions import execute_work_request
from daemons.fwrulesd.constants import FILTER_FAMILY_DATABASES, NAT_FAMILY_DATABASES
from daemons.svcmgmtd.supervisor import supervisor_status


ADGUARD_HOME_SERVICE_NAME = "adguardhome"
FILTERING_COLUMN = "adguardhome_upstream_enabled"
DNS_PROTOCOLS = ("tcp", "udp")


def filtering_requested() -> bool:
    """Return whether DNSMasq is configured to direct LAN DNS to AdGuard."""
    if not DNSMASQ_DB_PATH.exists():
        return False

    row = db.fetch_one(
        f"SELECT {FILTERING_COLUMN} AS enabled FROM dnsmasq_settings WHERE id = 1",
        db_path=DNSMASQ_DB_PATH,
    )
    return bool(row and int(row.get("enabled") or 0) == 1)


def adguard_is_running() -> bool:
    """Return whether AdGuard Home is currently able to accept DNS queries."""
    return supervisor_status(ADGUARD_HOME_SERVICE_NAME) == "RUNNING"


def replace_protected_dns_ports(port: int) -> None:
    """Replace protected DNS redirect and INPUT ports in persistent rule stores."""
    protocol_marks = ", ".join("?" for _ in DNS_PROTOCOLS)

    for db_path in NAT_FAMILY_DATABASES.values():
        with db.transaction(db_path) as conn:
            db.execute_on(
                conn,
                f"""
                UPDATE nat_prerouting_rules
                SET to_port = ?, updated_at = CURRENT_TIMESTAMP
                WHERE protected = 1
                  AND enabled = 1
                  AND nat_action = 'REDIRECT'
                  AND dst_port = ?
                  AND protocol_name IN ({protocol_marks})
                """,
                (port, DNSMASQ_DNS_PORT, *DNS_PROTOCOLS),
            )

    for db_path in FILTER_FAMILY_DATABASES.values():
        with db.transaction(db_path) as conn:
            db.execute_on(
                conn,
                f"""
                UPDATE filter_input_rules
                SET dst_port = ?, updated_at = CURRENT_TIMESTAMP
                WHERE protected = 1
                  AND enabled = 1
                  AND action = 'ACCEPT'
                  AND dst_port IN (?, ?)
                  AND protocol_name IN ({protocol_marks})
                """,
                (port, DNSMASQ_DNS_PORT, ADGUARD_HOME_DNS_PORT, *DNS_PROTOCOLS),
            )


def apply_table(family: str, category: str, table: str) -> None:
    """Flush and reapply one persisted firewall table immediately."""
    databases = NAT_FAMILY_DATABASES if category == "NAT_RULES" else FILTER_FAMILY_DATABASES
    db_path = databases[family]
    rows = db.fetch_all(
        f"SELECT id FROM {table} WHERE enabled = 1 AND COALESCE(pending_delete, 0) = 0 ORDER BY rule_order, id",
        db_path=db_path,
    )
    args = SimpleNamespace(
        category=category,
        family=family,
        action_name="apply",
        target_name=table,
    )
    execute_work_request(args, {"table": table, "rule_ids": [int(row["id"]) for row in rows]})


def sync_dns_filtering_redirect(adguard_running: bool | None = None) -> bool:
    """Apply the protected DNS target selected by configuration and service state."""
    active = filtering_requested() and (
        adguard_is_running() if adguard_running is None else adguard_running
    )
    target_port = ADGUARD_HOME_DNS_PORT if active else DNSMASQ_DNS_PORT
    replace_protected_dns_ports(target_port)

    for family in ("IPV4", "IPV6"):
        apply_table(family, "FIREWALL_RULES", "filter_input_rules")
        apply_table(family, "NAT_RULES", "nat_prerouting_rules")

    return active
