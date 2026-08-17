"""Validated kernel /proc parameter application for network interfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import db
from core.constants import COLLECTORD_IFACE_PROC_ITEMS, IFACE_DB_PATH
from core.process import command_exists, run_command


PROC_ROOT = Path("/proc/sys/net")
ALLOWED_PROC_ITEMS = {(family, key) for family, key, _ in COLLECTORD_IFACE_PROC_ITEMS}


def proc_path_for(iface_name: str, family: str, key: str) -> Path:
    """Return the permitted kernel proc path for an interface setting."""
    if not iface_name or Path(iface_name).name != iface_name or iface_name in {".", ".."}:
        raise ValueError("Invalid network interface name.")
    if (family, key) not in ALLOWED_PROC_ITEMS:
        raise ValueError("Unsupported kernel proc parameter.")
    return PROC_ROOT / family / "conf" / iface_name / key


def normalized_value(value: object) -> str:
    """Return an integer-only kernel proc value without shell interpretation."""
    rendered = str(value).strip()
    if not rendered or not rendered.isascii() or not rendered.isdecimal():
        raise ValueError("Kernel proc values must be non-negative integers.")
    return rendered


def apply_proc_value(payload: dict[str, Any]) -> None:
    """Write one validated interface setting to the kernel."""
    iface_name = str(payload.get("iface_name") or "").strip()
    requested_path = Path(str(payload.get("proc_path") or "").strip())
    value = normalized_value(payload.get("desired_value"))

    try:
        path_parts = requested_path.relative_to(PROC_ROOT).parts
    except ValueError as exc:
        raise ValueError("Invalid kernel proc path.") from exc
    if len(path_parts) != 4 or path_parts[1] != "conf" or path_parts[2] != iface_name:
        raise ValueError("Invalid kernel proc path.")
    family, key = path_parts[0], path_parts[3]

    expected_path = proc_path_for(iface_name, family, key)
    if requested_path != expected_path:
        raise ValueError("Kernel proc path does not match the selected interface.")
    if not expected_path.is_file():
        raise FileNotFoundError(f"Kernel proc parameter not found: {expected_path}")

    expected_path.write_text(f"{value}\n", encoding="utf-8")
    actual_value = expected_path.read_text(encoding="utf-8").strip()
    if actual_value != value:
        raise RuntimeError(f"Kernel proc parameter was not applied: {expected_path}")


def apply_interface_config(payload: dict[str, Any]) -> None:
    """Apply an interface MTU and persist its ArmFirewall metadata."""
    iface_name = str(payload.get("iface_name") or "").strip()
    role = str(payload.get("role") or "").strip().upper()
    description = str(payload.get("description") or "").strip()
    protected = int(payload.get("protected"))
    mtu = int(payload.get("mtu"))

    if not iface_name or Path(iface_name).name != iface_name or iface_name in {".", ".."}:
        raise ValueError("Invalid network interface name.")
    if role not in {"LAN", "WAN", "UNKNOWN"} or protected not in {0, 1} or not 68 <= mtu <= 65535:
        raise ValueError("Invalid network interface configuration.")
    if len(description) > 255:
        raise ValueError("Description must not exceed 255 characters.")
    if not (Path("/sys/class/net") / iface_name).is_dir():
        raise FileNotFoundError(f"Network interface not found: {iface_name}")
    if not command_exists("ip"):
        raise RuntimeError("The ip command is required to apply the interface MTU.")

    run_command(["ip", "link", "set", "dev", iface_name, "mtu", str(mtu)])
    with db.transaction(IFACE_DB_PATH) as conn:
        cursor = db.execute_on(
            conn,
            """
            UPDATE ifaces
            SET role = ?, description = ?, protected = ?, mtu = ?, collected_at = CURRENT_TIMESTAMP
            WHERE name = ?
            """,
            (role, description, protected, mtu, iface_name),
        )
        if cursor.rowcount == 0:
            raise LookupError("Network interface was not found in iface.db.")
