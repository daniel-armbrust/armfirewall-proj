"""Synchronize protected LAN DNS rules with the active local DNS service."""
from __future__ import annotations
from types import SimpleNamespace
from core import db
from core.constants import DNSMASQ_DB_PATH, DNSMASQ_DNS_PORT
from core.iface import get_lan_interface_names
from daemons.fwrulesd.actions import execute_work_request
from daemons.fwrulesd.constants import FILTER_FAMILY_DATABASES, NAT_FAMILY_DATABASES
from daemons.svcmgmtd.supervisor import supervisor_status

ADGUARD_HOME_SERVICE_NAME = "adguardhome"
DNS_PROTOCOLS = ("tcp", "udp")

def dns_requested() -> bool:
    if not DNSMASQ_DB_PATH.exists(): return False
    row = db.fetch_one("SELECT dns_enabled AS enabled FROM dnsmasq_settings WHERE id = 1", db_path=DNSMASQ_DB_PATH)
    return bool(row and int(row.get("enabled") or 0))

def adguard_is_running() -> bool:
    return supervisor_status(ADGUARD_HOME_SERVICE_NAME) == "RUNNING"

def ensure_nat_prerouting_schema(conn: db.Connection) -> None:
    columns = {str(row["name"]) for row in db.execute_on(conn, "PRAGMA table_info(nat_prerouting_rules)").fetchall()}
    if "pending_delete" not in columns:
        db.execute_on(conn, "ALTER TABLE nat_prerouting_rules ADD COLUMN pending_delete INTEGER NOT NULL DEFAULT 0 CHECK (pending_delete IN (0, 1))")

def ensure_lan_dns_input_rules() -> None:
    for family, db_path in FILTER_FAMILY_DATABASES.items():
        address = "::/0" if family == "IPV6" else "0.0.0.0/0"
        with db.transaction(db_path) as conn:
            for iface in get_lan_interface_names():
                for protocol in DNS_PROTOCOLS:
                    db.execute_on(conn, """INSERT INTO filter_input_rules (iface_in, rule_order, ct_new, ct_established, ct_related, ct_invalid, src_addr, src_port, dst_addr, dst_port, protocol_name, protocol_type, protocol_code, action, protected, rule_source, enabled, pending_delete, created_at, updated_at)
                    SELECT ?, (SELECT COALESCE(MAX(rule_order), 0) + 1 FROM filter_input_rules), 1,0,0,0,?,0,?,?,?,NULL,NULL,'ACCEPT',1,'system',1,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP
                    WHERE NOT EXISTS (SELECT 1 FROM filter_input_rules WHERE iface_in=? AND protocol_name=? AND dst_port=? AND action='ACCEPT' AND protected=1 AND rule_source='system' AND COALESCE(pending_delete,0)=0)""", (iface,address,address,DNSMASQ_DNS_PORT,protocol,iface,protocol,DNSMASQ_DNS_PORT))

def ensure_lan_dns_redirect_rules() -> None:
    for family, db_path in NAT_FAMILY_DATABASES.items():
        address = "::/0" if family == "IPV6" else "0.0.0.0/0"
        with db.transaction(db_path) as conn:
            ensure_nat_prerouting_schema(conn)
            for iface in get_lan_interface_names():
                for protocol in DNS_PROTOCOLS:
                    db.execute_on(conn, """INSERT INTO nat_prerouting_rules (iface_in,rule_order,src_addr,src_port,dst_addr,dst_port,protocol_name,protocol_type,protocol_code,nat_action,to_addr,to_port,protected,rule_source,enabled,pending_delete,created_at,updated_at)
                    SELECT ?, (SELECT COALESCE(MAX(rule_order),0)+1 FROM nat_prerouting_rules), ?,NULL,?,?,?,NULL,NULL,'REDIRECT',NULL,?,1,'system',1,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP
                    WHERE NOT EXISTS (SELECT 1 FROM nat_prerouting_rules WHERE iface_in=? AND protocol_name=? AND dst_port=? AND nat_action='REDIRECT' AND protected=1 AND rule_source='system' AND COALESCE(pending_delete,0)=0)""", (iface,address,address,DNSMASQ_DNS_PORT,protocol,DNSMASQ_DNS_PORT,iface,protocol,DNSMASQ_DNS_PORT))

def apply_table(family: str, category: str, table: str) -> None:
    databases = NAT_FAMILY_DATABASES if category == "NAT_RULES" else FILTER_FAMILY_DATABASES
    db_path = databases[family]
    rows = db.fetch_all(f"SELECT id FROM {table} WHERE enabled=1 AND COALESCE(pending_delete,0)=0 ORDER BY rule_order,id", db_path=db_path)
    execute_work_request(SimpleNamespace(category=category,family=family,action_name="apply",target_name=table), {"table":table,"rule_ids":[int(row["id"]) for row in rows]})

def sync_dns_routing(adguard_running: bool | None = None) -> bool:
    """Enable protected DNS forwarding only while DNSMasq or AdGuard owns DNS."""
    active = dns_requested() or (adguard_is_running() if adguard_running is None else adguard_running)
    ensure_lan_dns_input_rules(); ensure_lan_dns_redirect_rules()
    for db_path in NAT_FAMILY_DATABASES.values():
        with db.transaction(db_path) as conn:
            db.execute_on(conn, "UPDATE nat_prerouting_rules SET enabled=?, to_port=?, updated_at=CURRENT_TIMESTAMP WHERE nat_action='REDIRECT' AND dst_port=? AND protected=1 AND rule_source='system' AND COALESCE(pending_delete,0)=0 AND protocol_name IN ('tcp','udp')", (int(active),DNSMASQ_DNS_PORT,DNSMASQ_DNS_PORT))
    for family in ("IPV4","IPV6"):
        apply_table(family,"FIREWALL_RULES","filter_input_rules"); apply_table(family,"NAT_RULES","nat_prerouting_rules")
    return active
