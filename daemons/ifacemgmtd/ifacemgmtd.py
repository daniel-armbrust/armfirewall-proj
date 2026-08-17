"""One-shot executor for network interface and global kernel parameter changes."""

from __future__ import annotations

import argparse
import sys

from core import log as logger
from core.constants import (
    IFACEMGMTD_LOG_SOURCE,
    IFACE_PROC_WORK_REQUEST_ACTION,
    IFACE_PROC_WORK_REQUEST_CATEGORY,
    KERNEL_PARAMS_WORK_REQUEST_ACTION,
    KERNEL_PARAMS_WORK_REQUEST_CATEGORY,
)
from core.payload import decode_json_payload

from .applier import apply_global_kernel_param, apply_interface_config, apply_proc_value


def build_parser() -> argparse.ArgumentParser:
    """Build the standard work request executor argument parser."""
    parser = argparse.ArgumentParser(description="ArmFirewall interface configuration executor.")
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
    """Apply one queued interface or global kernel parameter change."""
    args = build_parser().parse_args()
    payload = decode_json_payload(args.payload_json)
    if (
        args.category_name == IFACE_PROC_WORK_REQUEST_CATEGORY
        and args.action_name == IFACE_PROC_WORK_REQUEST_ACTION
        and payload.get("operation") == "interface_config"
    ):
        apply_interface_config(payload)
        message = "Applied network interface configuration"
    elif args.category_name == IFACE_PROC_WORK_REQUEST_CATEGORY and args.action_name == IFACE_PROC_WORK_REQUEST_ACTION:
        apply_proc_value(payload)
        message = "Applied network interface kernel proc configuration"
    elif args.category_name == KERNEL_PARAMS_WORK_REQUEST_CATEGORY and args.action_name == KERNEL_PARAMS_WORK_REQUEST_ACTION:
        apply_global_kernel_param(str(payload.get("proc_path") or "").strip(), payload.get("current_value"))
        message = "Applied global network kernel parameter configuration"
    else:
        raise ValueError("Unsupported interface management work request.")

    logger.info(f"{message} work request {args.work_request_id}.", source=IFACEMGMTD_LOG_SOURCE)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - workreqd records executor failures.
        logger.error(str(exc), source=IFACEMGMTD_LOG_SOURCE)
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
