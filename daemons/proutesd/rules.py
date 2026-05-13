"""Policy routing rule operations for the policy routing executor."""

from __future__ import annotations

from core import db
from core.process import run_command

from .commons import add_if_value
from .constants import PROTECTED_RULE_PRIORITIES
from .models import RoutingRuleRow
from .routes import ip_command


def rule_is_immutable(rule: RoutingRuleRow) -> bool:
    """Return whether a routing rule is protected from GUI changes."""
    return int(rule.get("protected") or 0) == 1 or int(rule.get("priority") or -1) in PROTECTED_RULE_PRIORITIES


def fetch_rule(conn: db.Connection, rule_id: int) -> RoutingRuleRow:
    """Return one policy routing rule row from SQLite."""
    row = db.fetch_one_on(
        conn,
        """
        SELECT id, rule_order, addr_family, priority, source_addr, destination_addr,
               incoming_iface, outgoing_iface, fwmark, fwmask, tos, dsfield,
               ip_proto, sport, dport, uid_range, action, table_id,
               suppress_prefixlength, suppress_ifgroup, realms, goto_priority,
               protected, enabled, applied, pending_delete
        FROM routing_rules
        WHERE id = ?
        """,
        (rule_id,),
    )

    if row is None:
        raise RuntimeError(f"Routing rule not found: id={rule_id}")
    
    return db.row_to_dict(row)


def fetch_rules_for_table(conn: db.Connection, table_id: int) -> list[RoutingRuleRow]:
    """Return all policy routing rule rows that reference one routing table."""
    return db.fetch_all_on(
        conn,
        """
        SELECT id, rule_order, addr_family, priority, source_addr, destination_addr,
               incoming_iface, outgoing_iface, fwmark, fwmask, tos, dsfield,
               ip_proto, sport, dport, uid_range, action, table_id,
               suppress_prefixlength, suppress_ifgroup, realms, goto_priority,
               protected, enabled, applied, pending_delete
        FROM routing_rules
        WHERE table_id = ?
        ORDER BY id
        """,
        (table_id,),
    )


def rule_spec(rule: RoutingRuleRow) -> list[str]:
    """Build an iproute2 rule specification without the operation."""
    command = ["priority", str(rule["priority"])]

    add_if_value(command, "from", rule.get("source_addr"))
    add_if_value(command, "to", rule.get("destination_addr"))
    add_if_value(command, "iif", rule.get("incoming_iface"))
    add_if_value(command, "oif", rule.get("outgoing_iface"))

    fwmark = rule.get("fwmark")
    
    if fwmark:
        mark = str(fwmark).strip()
        
        if rule.get("fwmask"):
            mark = f"{mark}/{rule['fwmask']}"
        
        command.extend(["fwmark", mark])

    add_if_value(command, "tos", rule.get("tos") or rule.get("dsfield"))
    add_if_value(command, "ipproto", rule.get("ip_proto"))
    add_if_value(command, "sport", rule.get("sport"))
    add_if_value(command, "dport", rule.get("dport"))
    add_if_value(command, "uidrange", rule.get("uid_range"))

    action = str(rule.get("action") or "lookup").strip()
    
    if action == "lookup":
        command.extend(["lookup", str(rule["table_id"])])
    else:
        command.append(action)

    add_if_value(command, "suppress_prefixlength", rule.get("suppress_prefixlength"))
    add_if_value(command, "suppress_ifgroup", rule.get("suppress_ifgroup"))
    add_if_value(command, "realms", rule.get("realms"))
    add_if_value(command, "goto", rule.get("goto_priority"))

    return command


def remove_rule(rule: RoutingRuleRow) -> int:
    """Remove all matching operating system policy rule copies."""
    if rule_is_immutable(rule):
        raise RuntimeError(f"Protected routing rule cannot be removed: id={rule['id']}")
    
    removed = 0
    command = ip_command(str(rule["addr_family"]), "rule", "del", rule_spec(rule))
    
    while True:
        completed = run_command(command, check=False)
        
        if completed.returncode != 0:
            break
        
        removed += 1
    
    return removed


def apply_rule(rule: RoutingRuleRow) -> int:
    """Apply one enabled policy routing rule to the operating system."""
    if rule_is_immutable(rule):
        raise RuntimeError(f"Protected routing rule cannot be changed: id={rule['id']}")
    
    remove_rule(rule)
    run_command(ip_command(str(rule["addr_family"]), "rule", "add", rule_spec(rule)))
    
    return 1


def mark_rules_applied(conn: db.Connection, rule_ids: list[int], enabled: int) -> None:
    """Mark routing rule rows as applied after successful operating system changes."""
    if not rule_ids:
        return
    
    placeholders = ",".join("?" for _ in rule_ids)
    db.execute_on(
        conn,
        f"""
        UPDATE routing_rules
        SET enabled = ?, applied = 1, pending_delete = 0, updated_at = CURRENT_TIMESTAMP
        WHERE id IN ({placeholders})
        """,
        (enabled, *rule_ids),
    )


def purge_rules(conn: db.Connection, rule_ids: list[int]) -> int:
    """Delete routing rule rows that were successfully removed from the operating system."""
    if not rule_ids:
        return 0
    
    placeholders = ",".join("?" for _ in rule_ids)
    cursor = db.execute_on(conn, f"DELETE FROM routing_rules WHERE id IN ({placeholders})", tuple(rule_ids))
    
    return int(cursor.rowcount)
