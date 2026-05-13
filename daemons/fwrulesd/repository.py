"""SQLite access helpers for firewall rule work requests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import db

from .constants import PROTECTED_RULE_TABLES, RULE_DATABASES, SELECT_COLUMNS, TABLE_METADATA


def database_for_request(category: str, family: str) -> Path:
    """Return the SQLite database used by one rule work request."""
    db_path = RULE_DATABASES.get((category, family))

    if db_path is None:
        raise RuntimeError(f"Unsupported rule database mapping: category={category}, family={family}")

    return db_path


def verify_rule_database(category: str, family: str) -> None:
    """Verify that the rule database for one work request can be opened."""
    with db.connection(database_for_request(category, family)) as conn:
        db.fetch_one_on(conn, "SELECT 1")


def ensure_pending_delete_column(conn: db.Connection, table: str) -> None:
    """Add the pending delete marker to older rule tables when needed."""
    columns = {str(row["name"]) for row in db.execute_on(conn, f"PRAGMA table_info({table})").fetchall()}

    if "pending_delete" not in columns:
        db.execute_on(conn, f"ALTER TABLE {table} ADD COLUMN pending_delete INTEGER NOT NULL DEFAULT 0")


def table_from_request(args: Any, payload: dict[str, Any]) -> str:
    """Return the target SQLite table name for a request."""
    table = str(payload.get("table") or args.target_name or "").strip()

    if table not in TABLE_METADATA:
        raise RuntimeError(f"Unsupported rule table: {table}")

    return table


def fetch_protected_rules(category: str, family: str) -> list[dict[str, Any]]:
    """Return all enabled protected rules for one category and family."""
    db_path = database_for_request(category, family)
    rules: list[dict[str, Any]] = []

    with db.transaction(db_path) as conn:
        for table in PROTECTED_RULE_TABLES[category]:
            ensure_pending_delete_column(conn, table)

            columns = SELECT_COLUMNS[table]

            rows = db.fetch_all_on(
                conn,
                f"""
                SELECT {columns}
                FROM {table}
                WHERE protected = 1
                  AND enabled = 1
                  AND COALESCE(pending_delete, 0) = 0
                ORDER BY rule_order, id
                """,
            )

            for row in rows:
                rule = dict(row)
                rule["family"] = family
                rule["table"] = table
                rules.append(rule)

    return rules


def purge_pending_delete_rules(args: Any, table: str, payload: dict[str, Any]) -> int:
    """Remove rules from SQLite after a successful full chain apply."""
    rule_ids = payload.get("delete_rule_ids")

    if not isinstance(rule_ids, list) or not rule_ids:
        return 0

    placeholders = ",".join("?" for _ in rule_ids)
    with db.transaction(database_for_request(args.category, args.family)) as conn:
        cursor = db.execute_on(
            conn,
            f"DELETE FROM {table} WHERE pending_delete = 1 AND id IN ({placeholders})",
            tuple(int(rule_id) for rule_id in rule_ids),
        )

        return int(cursor.rowcount)


def delete_failed_rule(args: Any, table: str, rule: dict[str, Any]) -> int:
    """Delete a non-protected rule that failed during a full chain apply."""
    if int(rule.get("protected") or 0) == 1 or rule.get("id") is None:
        return 0

    with db.transaction(database_for_request(args.category, args.family)) as conn:
        cursor = db.execute_on(conn, f"DELETE FROM {table} WHERE id = ?", (int(rule["id"]),))
        return int(cursor.rowcount)


def fetch_rule(args: Any, table: str, rule_id: int) -> dict[str, Any]:
    """Read one enabled or disabled rule from its SQLite table."""
    columns = SELECT_COLUMNS.get(table)

    if not columns:
        raise RuntimeError(f"Unsupported rule table: {table}")

    with db.connection(database_for_request(args.category, args.family)) as conn:
        row = db.fetch_one_on(conn, f"SELECT {columns} FROM {table} WHERE id = ?", (rule_id,))

    if row is None:
        raise RuntimeError(f"Rule not found: table={table}, id={rule_id}")

    rule = db.row_to_dict(row)
    rule["family"] = args.family
    rule["table"] = table

    return rule


def rules_for_payload(args: Any, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve the rules affected by a work request payload."""
    table = table_from_request(args, payload)
    rule_ids = payload.get("rule_ids")

    if isinstance(payload.get("rule"), dict):
        rule = dict(payload["rule"])
        rule.setdefault("table", table)
        rule.setdefault("family", args.family)

        return [rule]

    if isinstance(rule_ids, list):
        return [fetch_rule(args, table, int(rule_id)) for rule_id in rule_ids]

    if args.target_rule_id:
        return [fetch_rule(args, table, int(args.target_rule_id))]

    if payload.get("rule_id"):
        return [fetch_rule(args, table, int(payload["rule_id"]))]

    return []
