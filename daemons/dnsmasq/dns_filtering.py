"""Synchronize system-managed DNS rules with the configured filtering mode."""

from __future__ import annotations

from types import SimpleNamespace

from core import db
from core.constants import ADGUARD_HOME_DNS_PORT, DNSMASQ_DB_PATH, DNSMASQ_DNS_PORT
from core.iface import get_lan_interface_names
from daemons.fwrulesd.actions import execute_work_request
from daemons.fwrulesd.constants import FILTER_FAMILY_DATABASES, NAT_FAMILY_DATABASES
from daemons.svcmgmtd.supervisor import supervisor_status


ADGUARD_HOME_SERVICE_NAME = "adguardhome"
FILTERING_COLUMN = "adguardhome_upstream_enabled"
DNS_ENABLED_COLUMN = "dns_enabled"
DNS_PROTOCOLS = ("tcp", "udp")


def dns_requested() -> bool:
    """Return whether DNSMasq DNS service is enabled."""
    if not DNSMASQ_DB_PATH.exists():
        return False

    row = db.fetch_one(
        f"SELECT {DNS_ENABLED_COLUMN} AS enabled FROM dnsmasq_settings WHERE id = 1",
        db_path=DNSMASQ_DB_PATH,
    )
    return bool(row and int(row.get("enabled") or 0) == 1)


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


def ensure_adguard_lan_input_rules() -> None:
    """Create protected TCP and UDP 5353 INPUT rules for every LAN interface."""
    lan_interfaces = get_lan_interface_names()
    if not lan_interfaces:
        return

    for family, db_path in FILTER_FAMILY_DATABASES.items():
        any_address = "::/0" if family == "IPV6" else "0.0.0.0/0"
        with db.transaction(db_path) as conn:
            for iface in lan_interfaces:
                for protocol in DNS_PROTOCOLS:
                    db.execute_on(
                        conn,
                        """
                        INSERT INTO filter_input_rules (
                            iface_in, rule_order, ct_new, ct_established, ct_related,
                            ct_invalid, src_addr, src_port, dst_addr, dst_port,
                            protocol_name, protocol_type, protocol_code, action,
                            protected, rule_source, enabled, pending_delete, created_at, updated_at
                        )
                        SELECT
                            ?, (SELECT COALESCE(MAX(rule_order), 0) + 1 FROM filter_input_rules),
                            1, 0, 0, 0, ?, 0, ?, ?, ?, NULL, NULL, 'ACCEPT',
                            1, 'system', 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM filter_input_rules
                            WHERE iface_in = ?
                              AND protocol_name = ?
                              AND dst_port = ?
                              AND action = 'ACCEPT'
                              AND protected = 1
                              AND COALESCE(pending_delete, 0) = 0
                        )
                        """,
                        (
                            iface,
                            any_address,
                            any_address,
                            ADGUARD_HOME_DNS_PORT,
                            protocol,
                            iface,
                            protocol,
                            ADGUARD_HOME_DNS_PORT,
                        ),
                    )



def ensure_dnsmasq_lan_redirect_rules() -> None:
    """Create protected DNS REDIRECT rules for every LAN interface."""
    lan_interfaces = get_lan_interface_names()
    if not lan_interfaces:
        return

    for family, db_path in NAT_FAMILY_DATABASES.items():
        any_address = "::/0" if family == "IPV6" else "0.0.0.0/0"
        with db.transaction(db_path) as conn:
            for iface in lan_interfaces:
                for protocol in DNS_PROTOCOLS:
                    db.execute_on(
                        conn,
                        """
                        INSERT INTO nat_prerouting_rules (
                            iface_in, rule_order, src_addr, src_port, dst_addr, dst_port,
                            protocol_name, protocol_type, protocol_code,
                            nat_action, to_addr, to_port,
                            protected, rule_source, enabled, pending_delete, created_at, updated_at
                        )
                        SELECT
                            ?, (SELECT COALESCE(MAX(rule_order), 0) + 1 FROM nat_prerouting_rules),
                            ?, NULL, ?, ?, ?, NULL, NULL,
                            'REDIRECT', NULL, ?,
                            1, 'system', 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        WHERE NOT EXISTS (
                            SELECT 1 FROM nat_prerouting_rules
                            WHERE iface_in = ?
                              AND protocol_name = ?
                              AND dst_port = ?
                              AND nat_action = 'REDIRECT'
                              AND protected = 1
                              AND rule_source = 'system'
                              AND COALESCE(pending_delete, 0) = 0
                        )
                        """,
                        (iface, any_address, any_address, DNSMASQ_DNS_PORT,
                         protocol, DNSMASQ_DNS_PORT, iface, protocol, DNSMASQ_DNS_PORT),
                    )

def sync_managed_dns_redirect(port: int, *, enabled: bool) -> None:
    """Set protected LAN DNS REDIRECT rules to the selected local DNS listener."""
    protocol_marks = ", ".join("?" for _ in DNS_PROTOCOLS)

    for db_path in NAT_FAMILY_DATABASES.values():
        with db.transaction(db_path) as conn:
            db.execute_on(
                conn,
                f"""
                UPDATE nat_prerouting_rules
                SET to_port = ?, protected = 1, rule_source = 'system',
                    enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE (protected = 1 OR rule_source = 'system')
                  AND COALESCE(pending_delete, 0) = 0
                  AND nat_action = 'REDIRECT'
                  AND dst_port = ?
                  AND protocol_name IN ({protocol_marks})
                """,
                (port, int(enabled), DNSMASQ_DNS_PORT, *DNS_PROTOCOLS),
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
    """Apply protected LAN DNS redirects according to DNSMasq and AdGuard state."""
    dns_enabled = dns_requested()
    active = dns_enabled and filtering_requested() and (
        adguard_is_running() if adguard_running is None else adguard_running
    )
    target_port = ADGUARD_HOME_DNS_PORT if active else DNSMASQ_DNS_PORT
    ensure_adguard_lan_input_rules()
    ensure_dnsmasq_lan_redirect_rules()
    sync_managed_dns_redirect(target_port, enabled=dns_enabled)

    for family in ("IPV4", "IPV6"):
        apply_table(family, "FIREWALL_RULES", "filter_input_rules")
        apply_table(family, "NAT_RULES", "nat_prerouting_rules")

    return active
