"""Filter chain policy database helpers."""

from __future__ import annotations

from core import db


FILTER_RULE_TABLES = {
    "filter_input_rules": ("iface_in TEXT NOT NULL,", "iface_in,"),
    "filter_forward_rules": ("iface_in TEXT NOT NULL,\n     iface_out TEXT NOT NULL,", "iface_in, iface_out,"),
    "filter_output_rules": ("iface_out TEXT NOT NULL,", "iface_out,"),
}


def filter_rule_table_sql(table: str, iface_columns: str, protocol_name: str) -> str:
    """Return filter rule table DDL with ESP protocol support."""
    return f"""
CREATE TABLE {table} (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     {iface_columns}
     rule_order INTEGER NOT NULL,
     ct_new INTEGER NOT NULL DEFAULT 0 CHECK (ct_new IN (0, 1)),
     ct_established INTEGER NOT NULL DEFAULT 0 CHECK (ct_established IN (0, 1)),
     ct_related INTEGER NOT NULL DEFAULT 0 CHECK (ct_related IN (0, 1)),
     ct_invalid INTEGER NOT NULL DEFAULT 0 CHECK (ct_invalid IN (0, 1)),
     src_addr TEXT NOT NULL,
     src_port INTEGER,
     dst_addr TEXT NOT NULL,
     dst_port INTEGER,
     protocol_name TEXT NOT NULL,
     protocol_type INTEGER,
     protocol_code INTEGER,
     action TEXT NOT NULL DEFAULT 'DROP' CHECK (action IN ('DROP', 'REJECT', 'ACCEPT')),
     protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
     enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
     created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
     pending_delete INTEGER NOT NULL DEFAULT 0,
     FOREIGN KEY (protocol_name) REFERENCES protocols(name),
     CHECK (
          (
               protocol_name IN ('tcp', 'udp')
               AND src_port IS NOT NULL
               AND dst_port IS NOT NULL
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name IN ('all', 'esp')
               AND src_port IS NULL
               AND dst_port IS NULL
               AND protocol_type IS NULL
               AND protocol_code IS NULL
          )
          OR
          (
               protocol_name = '{protocol_name}'
               AND src_port IS NULL
               AND dst_port IS NULL
          )
     ),
     CHECK (
          (protocol_type IS NULL AND protocol_code IS NULL)
          OR
          (protocol_type IS NOT NULL AND protocol_code IS NOT NULL)
     )
)
"""


def rule_table_columns(conn: db.Connection, table: str, iface_select: str) -> str:
    """Return shared columns for copying one filter rule table."""
    existing_columns = {str(row["name"]) for row in db.execute_on(conn, f"PRAGMA table_info({table})").fetchall()}
    pending_delete = "pending_delete" if "pending_delete" in existing_columns else "0 AS pending_delete"
    return (
        f"id, {iface_select} rule_order, ct_new, ct_established, ct_related, ct_invalid, "
        "src_addr, src_port, dst_addr, dst_port, protocol_name, protocol_type, protocol_code, "
        f"action, protected, enabled, created_at, updated_at, {pending_delete}"
    )


def ensure_esp_protocol_support(conn: db.Connection) -> None:
    """Upgrade older filter rule databases so ESP can be stored."""
    row = db.fetch_one_on(
        conn,
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'filter_input_rules'",
    )

    if row is None or "'esp'" in str(row["sql"]):
        return

    protocol_row = db.fetch_one_on(conn, "SELECT name FROM protocols WHERE name IN ('icmp', 'icmpv6') LIMIT 1")
    icmp_protocol = str(protocol_row["name"] if protocol_row else "icmp")

    db.execute_on(conn, "PRAGMA foreign_keys = OFF")
    db.execute_on(conn, "ALTER TABLE protocols RENAME TO protocols_old")
    db.execute_on(
        conn,
        f"""
        CREATE TABLE protocols (
             name TEXT PRIMARY KEY CHECK (name IN ('all', 'tcp', 'udp', '{icmp_protocol}', 'esp')),
             description TEXT NOT NULL
        )
        """,
    )
    db.execute_on(conn, "INSERT INTO protocols (name, description) SELECT name, description FROM protocols_old")
    db.execute_on(conn, "INSERT OR IGNORE INTO protocols (name, description) VALUES ('esp', 'Encapsulating Security Payload')")
    db.execute_on(conn, "DROP TABLE protocols_old")

    for table, (iface_columns, iface_select) in FILTER_RULE_TABLES.items():
        copy_columns = rule_table_columns(conn, table, iface_select)
        db.execute_on(conn, f"ALTER TABLE {table} RENAME TO {table}_old")
        db.execute_on(conn, filter_rule_table_sql(table, iface_columns, icmp_protocol))
        db.execute_on(conn, f"INSERT INTO {table} ({copy_columns.replace('0 AS pending_delete', 'pending_delete')}) SELECT {copy_columns} FROM {table}_old")
        db.execute_on(conn, f"DROP TABLE {table}_old")

    db.execute_on(conn, "PRAGMA foreign_keys = ON")


def require_filter_chain_policies(conn: db.Connection) -> None:
    """Fail clearly when the filter chain policy table was not created."""
    row = db.fetch_one_on(
        conn,
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'filter_chain_policies'",
    )

    if row is None:
        raise RuntimeError("Missing filter_chain_policies table. Run install.sh to create the firewall schema.")

    ensure_esp_protocol_support(conn)
