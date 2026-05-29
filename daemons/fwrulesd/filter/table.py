"""Filter table rule helpers for the firewall rule executor."""

from __future__ import annotations

from typing import Any

from core import db
from core.process import run_command

from ..commons import command_name
from ..constants import (
    DEFAULT_FILTER_POLICIES,
    FILTER_BUILTIN_CHAINS,
    FILTER_POLICIES,
    FILTER_RULE_TABLES,
    RULE_DATABASES,
    TABLE_METADATA,
)
from .policies import require_filter_chain_policies
from ..repository import ensure_pending_delete_column


def rule_action(rule: dict[str, Any]) -> str:
    """Return the filter target action for one rule."""
    return str(rule.get("action") or "ACCEPT").upper()


def filter_database_for_family(family: str) -> Any:
    """Return the filter rules database path for one address family."""
    db_path = RULE_DATABASES.get(("FIREWALL_RULES", family))

    if db_path is None:
        raise RuntimeError(f"Unsupported filter rule database mapping: family={family}")
    
    return db_path



def wildcard_address_for_family(family: str) -> str:
    """Return the wildcard source/destination address for one family."""
    return "::/0" if family == "IPV6" else "0.0.0.0/0"


def ensure_base_conntrack_rule(family: str, table_name: str) -> dict[str, Any] | None:
    """Persist the base return-traffic rule required after chain flushes."""
    if table_name not in {"filter_input_rules", "filter_forward_rules"}:
        return None

    db_path = filter_database_for_family(family)
    any_addr = wildcard_address_for_family(family)
    has_iface_out = table_name == "filter_forward_rules"
    iface_out_column = "iface_out, " if has_iface_out else ""
    iface_out_value = "'ANY', " if has_iface_out else ""
    iface_out_match = "AND iface_out = 'ANY'" if has_iface_out else ""
    iface_out_select = "iface_out" if has_iface_out else "'' AS iface_out"

    with db.transaction(db_path) as conn:
        ensure_pending_delete_column(conn, table_name)
        db.execute_on(
            conn,
            f"""
            INSERT INTO {table_name} (
                iface_in, {iface_out_column}rule_order,
                ct_new, ct_established, ct_related, ct_invalid,
                src_addr, src_port, dst_addr, dst_port,
                protocol_name, protocol_type, protocol_code, action,
                protected, enabled, created_at, updated_at
            )
            SELECT
                'ANY', {iface_out_value}
                (SELECT COALESCE(MIN(rule_order), 1) - 1 FROM {table_name}),
                0, 1, 1, 0,
                ?, NULL, ?, NULL,
                'all', NULL, NULL, 'ACCEPT',
                0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1
                FROM {table_name}
                WHERE iface_in = 'ANY'
                  {iface_out_match}
                  AND protocol_name = 'all'
                  AND ct_established = 1
                  AND ct_related = 1
                  AND action = 'ACCEPT'
                  AND enabled = 1
                  AND COALESCE(pending_delete, 0) = 0
            )
            """,
            (any_addr, any_addr),
        )

        row = db.fetch_one_on(
            conn,
            f"""
            SELECT id, rule_order, iface_in,
                   {iface_out_select},
                   ct_new, ct_established, ct_related, ct_invalid,
                   src_addr, src_port, dst_addr, dst_port,
                   protocol_name, protocol_type, protocol_code,
                   action, protected, enabled, created_at, updated_at
            FROM {table_name}
            WHERE iface_in = 'ANY'
              {iface_out_match}
              AND protocol_name = 'all'
              AND ct_established = 1
              AND ct_related = 1
              AND action = 'ACCEPT'
              AND enabled = 1
              AND COALESCE(pending_delete, 0) = 0
            ORDER BY rule_order, id
            LIMIT 1
            """,
        )

    if row is None:
        return None

    rule = db.row_to_dict(row)
    rule["family"] = family
    rule["table"] = table_name

    return rule


def filter_policy_for_chain(family: str, chain: str) -> str:
    """Return the persisted filter policy for one family and chain."""
    with db.connection(filter_database_for_family(family)) as conn:
        require_filter_chain_policies(conn)

        row = db.fetch_one_on(
            conn,
            "SELECT policy FROM filter_chain_policies WHERE chain_name = ?",
            (chain,),
        )

    if row is None:
        return DEFAULT_FILTER_POLICIES[chain]
    
    policy = str(row["policy"]).upper()

    return policy if policy in FILTER_POLICIES else DEFAULT_FILTER_POLICIES[chain]


def remove_reject_policy_tail(family: str, chain: str) -> int:
    """Remove ArmFirewall managed REJECT policy tail rules."""
    removed = 0
    command = command_name(family)
    
    delete = [
        command,
        "-t",
        "filter",
        "-D",
        chain,
        "-m",
        "comment",
        "--comment",
        "armfirewall-policy-reject",
        "-j",
        "REJECT",
    ]

    while run_command(delete, check=False).returncode == 0:
        removed += 1

    return removed


def enforce_configured_filter_policies() -> int:
    """Ensure filter built-in chains use the policies stored in SQLite."""
    changed = 0

    for family in ("IPV4", "IPV6"):
        command = command_name(family)

        for chain in FILTER_BUILTIN_CHAINS:
            policy = filter_policy_for_chain(family, chain)
            row = run_command([command, "-t", "filter", "-S", chain], check=False)
            expected = f"-P {chain} {policy}"
            changed += remove_reject_policy_tail(family, chain)

            if row.returncode == 0 and expected in row.stdout.splitlines():
                continue

            run_command([command, "-t", "filter", "-P", chain, policy])
            
            changed += 1

    return changed


def apply_payload_filter_policy(args: Any, table_name: str, payload: dict[str, Any]) -> int:
    """Apply the requested filter policy for a full chain work request."""
    if args.category != "FIREWALL_RULES" or table_name not in FILTER_RULE_TABLES:
        return 0
    
    _, chain = TABLE_METADATA[table_name]

    policy = str(payload.get("policy") or filter_policy_for_chain(args.family, chain)).upper()

    if policy not in FILTER_POLICIES:
        raise RuntimeError(f"Unsupported filter policy: {policy}")
    
    remove_reject_policy_tail(args.family, chain)
    run_command([command_name(args.family), "-t", "filter", "-P", chain, policy])
    
    return 1
