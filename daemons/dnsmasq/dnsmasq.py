#!/usr/bin/env python3
"""One-shot Dnsmasq configuration renderer used by the work request daemon."""

from __future__ import annotations

import argparse
import sys

from .constants import DNSMASQ_DB_PATH, LOG_SOURCE, WORK_REQUEST_DB_PATH
from .models import DnsmasqWorkRequest

from core import db
from core import log as logger
from core.constants import DNSMASQ_CONF_PATH, DNSMASQ_LEASES_PATH
from core.payload import decode_json_payload
from web.services.dnsmasq import api as dnsmasq_config
from .dns_filtering import sync_dns_filtering_redirect
from .resolver import configure_system_resolver
from daemons.svcmgmtd.supervisor import supervisor_command, supervisor_status


def request_from_args(args: argparse.Namespace) -> DnsmasqWorkRequest:
    """Return a normalized Dnsmasq work request from CLI arguments."""
    return DnsmasqWorkRequest(
        work_request_id=str(args.work_request_id),
        request_uid=str(args.request_uid),
        category_name=str(args.category_name),
        category=str(args.category),
        family=str(args.family or ""),
        target_name=str(args.target_name),
        action_name=str(args.action_name),
        target_rule_id=str(args.target_rule_id or ""),
        payload=decode_json_payload(args.payload_json),
    )


def validate_request(request: DnsmasqWorkRequest) -> None:
    """Ensure this executor supports the requested Dnsmasq action."""
    if request.category != "SERVICE_MANAGEMENT" or request.target_name != "dnsmasq_config":
        raise RuntimeError(f"Unsupported category for dnsmasq.py: {request.category}/{request.target_name}")
    if request.action_name != "apply":
        raise RuntimeError(f"Unsupported Dnsmasq action: {request.action_name}")


def write_dnsmasq_conf(config_text: str) -> None:
    """Atomically write the rendered dnsmasq.conf file."""
    DNSMASQ_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = DNSMASQ_CONF_PATH.with_suffix(".conf.tmp")
    tmp_path.write_text(config_text, encoding="utf-8")
    tmp_path.replace(DNSMASQ_CONF_PATH)


def reload_running_dnsmasq() -> None:
    """Reload DNSMasq only when it was already running."""
    if supervisor_status("dnsmasq") != "RUNNING":
        return

    supervisor_command("restart", "dnsmasq", timeout=60)
    if supervisor_status("dnsmasq") != "RUNNING":
        raise RuntimeError("Dnsmasq did not return to RUNNING after configuration apply.")


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
    DNSMASQ_LEASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    config = dnsmasq_config.load_config_from_db()
    if config is None:
        raise RuntimeError("No Dnsmasq configuration was found in dnsmasq.db.")

    config_text = dnsmasq_config.render_config(config)
    ok, message = dnsmasq_config.validate_dnsmasq_syntax(config_text)
    if not ok:
        raise RuntimeError(message)

    write_dnsmasq_conf(config_text)
    configure_system_resolver(bool(config.get("dns_enabled")))
    reload_running_dnsmasq()
    filtering_active = sync_dns_filtering_redirect()
    clear_pending_apply()
    logger.log(
        f"Dnsmasq configuration file was rendered from SQLite; DNS filtering active={filtering_active}.",
        source=LOG_SOURCE,
    )


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
    request = request_from_args(args)
    validate_request(request)
    db.verify_databases(DNSMASQ_DB_PATH, WORK_REQUEST_DB_PATH)
    apply_config()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - workreqd captures stderr.
        logger.error(str(exc), source=LOG_SOURCE)
        print(str(exc), file=sys.stderr)
        sys.exit(1)
