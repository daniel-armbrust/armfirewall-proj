#!/usr/bin/env python3
"""One-shot BIRD configuration renderer used by the work request daemon."""

from __future__ import annotations

import argparse
import shutil
import sys

from .constants import BIRD_CONF, BIRD_DB_PATH, LOG_SOURCE, WORK_REQUEST_DB_PATH
from .models import BirdWorkRequest

from core import db
from core import log as logger
from core.payload import decode_json_payload
from web.services.routingprotocols import api as bird_config


def request_from_args(args: argparse.Namespace) -> BirdWorkRequest:
    """Return a normalized BIRD work request from CLI arguments."""
    return BirdWorkRequest(
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


def validate_request(request: BirdWorkRequest) -> None:
    """Ensure this executor supports the requested BIRD action."""
    if request.category != "SERVICE_MANAGEMENT" or request.target_name != "bird_config":
        raise RuntimeError(f"Unsupported category for bird.py: {request.category}/{request.target_name}")
    
    if request.action_name != "apply":
        raise RuntimeError(f"Unsupported BIRD action: {request.action_name}")


def write_bird_conf(config_text: str) -> None:
    """Atomically write the rendered bird.conf file."""
    BIRD_CONF.parent.mkdir(parents=True, exist_ok=True)
    
    if BIRD_CONF.exists():
        backup_path = BIRD_CONF.with_suffix(BIRD_CONF.suffix + ".armfw.bak")
        shutil.copy2(BIRD_CONF, backup_path)
    
    tmp_path = BIRD_CONF.with_suffix(BIRD_CONF.suffix + ".tmp")
    tmp_path.write_text(config_text, encoding="utf-8")
    tmp_path.replace(BIRD_CONF)


def apply_config() -> None:
    """Render SQLite BIRD settings to conf/bird.conf only."""
    settings = bird_config.settings_from_db()
    rip_settings = bird_config.rip_settings_from_db()
    
    write_bird_conf(bird_config.render_global_config(settings, rip_settings))
    
    logger.log("BIRD configuration file was rendered from SQLite.", source=LOG_SOURCE)


def build_parser() -> argparse.ArgumentParser:
    """Build the work request executor argument parser."""
    parser = argparse.ArgumentParser(description="ArmFirewall BIRD configuration executor.")
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
    """Execute one BIRD work request."""
    args = build_parser().parse_args()
    request = request_from_args(args)
    
    validate_request(request)
    
    db.verify_databases(BIRD_DB_PATH, WORK_REQUEST_DB_PATH)
    apply_config()
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - workreqd captures stderr.
        logger.error(str(exc), source=LOG_SOURCE)
        print(str(exc), file=sys.stderr)
        sys.exit(1)
