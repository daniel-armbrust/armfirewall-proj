"""One-shot executor for global network kernel parameter work requests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core import log as logger
from core.constants import (
    COLLECTORD_LOG_SOURCE,
    KERNEL_PARAMS_WORK_REQUEST_ACTION,
    KERNEL_PARAMS_WORK_REQUEST_CATEGORY,
)
from core.payload import decode_json_payload
from web.network.kernel_params import param_by_path

from .collectors.iface.applier import normalized_value


def build_parser() -> argparse.ArgumentParser:
    """Build the standard work request executor argument parser."""
    parser = argparse.ArgumentParser(description="ArmFirewall global kernel parameter executor.")
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


def apply_kernel_param(proc_path: str, current_value: object) -> None:
    """Apply one registry-approved global kernel parameter value."""
    param = param_by_path(proc_path)
    value = normalized_value(current_value)
    path = Path(param.proc_path)
    if not path.is_file():
        raise FileNotFoundError(f"Kernel parameter not found: {path}")
    path.write_text(f"{value}\n", encoding="utf-8")
    if path.read_text(encoding="utf-8").strip() != value:
        raise RuntimeError(f"Kernel parameter was not applied: {path}")


def main() -> int:
    """Apply one queued global kernel parameter change."""
    args = build_parser().parse_args()
    if args.category_name != KERNEL_PARAMS_WORK_REQUEST_CATEGORY or args.action_name != KERNEL_PARAMS_WORK_REQUEST_ACTION:
        raise ValueError("Unsupported global kernel parameter work request.")
    payload = decode_json_payload(args.payload_json)
    apply_kernel_param(str(payload.get("proc_path") or "").strip(), payload.get("current_value"))
    logger.info(f"Applied global kernel parameter work request {args.work_request_id}.", source=COLLECTORD_LOG_SOURCE)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - workreqd records executor failures.
        logger.error(str(exc), source=COLLECTORD_LOG_SOURCE)
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
