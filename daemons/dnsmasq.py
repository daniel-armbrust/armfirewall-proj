#!/usr/bin/env python3
"""One-shot Dnsmasq configuration renderer used by the work request daemon."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import db
from core import log as logger
from web.services.dnsmasq import dnsmasq as dnsmasq_config


DNSMASQ_DB_PATH = ROOT_DIR / "db" / "dnsmasq.db"
WORK_REQUEST_DB_PATH = ROOT_DIR / "db" / "work-requests.db"
DNSMASQ_CONF = ROOT_DIR / "conf" / "dnsmasq.conf"
LOG_SOURCE = "dnsmasq.py"


def verify_databases() -> None:
    """Verify that required SQLite databases are available."""
    with db.connection(DNSMASQ_DB_PATH) as conn:
        db.fetch_one_on(conn, "SELECT 1")
    with db.connection(WORK_REQUEST_DB_PATH) as conn:
        db.fetch_one_on(conn, "SELECT 1")


def payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Decode the work request JSON payload."""
    try:
        payload = json.loads(args.payload_json or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid payload JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Payload JSON must decode to an object.")
    return payload


def write_dnsmasq_conf(config_text: str) -> None:
    """Atomically write the rendered dnsmasq.conf file."""
    DNSMASQ_CONF.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = DNSMASQ_CONF.with_suffix(".conf.tmp")
    tmp_path.write_text(config_text, encoding="utf-8")
    tmp_path.replace(DNSMASQ_CONF)


def clear_pending_apply() -> None:
    """Mark the persisted Dnsmasq configuration as applied."""
    with db.transaction(DNSMASQ_DB_PATH) as conn:
        db.execute_on(
            conn,
            """
            UPDATE dnsmasq_settings
            SET pending_apply = 0, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
        )


def apply_config() -> None:
    """Render SQLite Dnsmasq settings to conf/dnsmasq.conf only."""
    config = dnsmasq_config.load_config_from_db()
    if config is None:
        raise RuntimeError("No Dnsmasq configuration was found in dnsmasq.db.")

    config_text = dnsmasq_config.render_config(config)
    ok, message = dnsmasq_config.validate_dnsmasq_syntax(config_text)
    if not ok:
        raise RuntimeError(message)

    write_dnsmasq_conf(config_text)
    clear_pending_apply()
    logger.log("Dnsmasq configuration file was rendered from SQLite.", source=LOG_SOURCE)


def build_parser() -> argparse.ArgumentParser:
    """Build the work request executor argument parser."""
    parser = argparse.ArgumentParser(description="ArmFirewall Dnsmasq configuration executor.")
    parser.add_argument("--work-request-id", required=True)
    parser.add_argument("--request-uid", required=True)
    parser.add_argument("--category-name", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--family", required=False)
    parser.add_argument("--target-name", required=True)
    parser.add_argument("--action-name", required=True)
    parser.add_argument("--target-rule-id", required=False)
    parser.add_argument("--payload-json", required=True)
    return parser


def main() -> int:
    """Execute one Dnsmasq work request."""
    args = build_parser().parse_args()
    if args.category != "SERVICE_MANAGEMENT" or args.target_name != "dnsmasq_config":
        raise RuntimeError(f"Unsupported category for dnsmasq.py: {args.category}/{args.target_name}")
    if args.action_name != "apply":
        raise RuntimeError(f"Unsupported Dnsmasq action: {args.action_name}")

    payload_from_args(args)
    verify_databases()
    apply_config()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - workreqd captures stderr.
        logger.error(str(exc), source=LOG_SOURCE)
        print(str(exc), file=sys.stderr)
        sys.exit(1)
