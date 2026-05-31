from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from web.services.api import service_installed, service_status_by_name


BIRD_CONFIG_CANDIDATES = (Path("/etc/bird/bird.conf"), Path("/etc/bird.conf"))
DEFAULT_ROUTER_ID = "192.0.2.1"
IMPORT_EXPORT_VALUES = {"all", "none"}


def bird_config_path() -> Path:
    """Return the preferred BIRD configuration path for this host."""
    for path in BIRD_CONFIG_CANDIDATES:
        if path.exists():
            return path
    return BIRD_CONFIG_CANDIDATES[0]


def bird_service_installed() -> bool:
    """Return whether the BIRD routing daemon is installed."""
    return service_installed("bird")


def bird_version() -> str:
    """Return the installed BIRD daemon version."""
    for command in (["bird", "--version"], ["/usr/sbin/bird", "--version"]):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        output = (result.stdout or result.stderr or "").strip()
        if output:
            first_line = output.splitlines()[0]
            match = re.search(r"(\d+(?:\.\d+)+)", first_line)
            return match.group(1) if match else first_line
    return "-"


def bird_status() -> dict[str, Any]:
    """Return the persisted BIRD optional service status."""
    try:
        return service_status_by_name("bird")
    except ValueError:
        return {
            "name": "bird",
            "display_name": "BIRD Routing Daemon",
            "installed": False,
            "state": "NOT INSTALLED",
            "details": "Missing from service catalog.",
        }


def int_setting(value: Any, *, default: int, minimum: int, maximum: int, field: str) -> int:
    """Normalize one bounded integer setting."""
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be an integer.") from exc
    if parsed < minimum or parsed > maximum:
        raise HTTPException(status_code=400, detail=f"{field} must be between {minimum} and {maximum}.")
    return parsed


def bool_setting(value: Any) -> bool:
    """Normalize a boolean-ish payload field."""
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def import_export_setting(value: Any, *, field: str) -> str:
    """Normalize one BIRD import/export policy value."""
    text = str(value or "none").strip().lower()
    if text not in IMPORT_EXPORT_VALUES:
        raise HTTPException(status_code=400, detail=f"{field} must be all or none.")
    return text


def router_id_setting(value: Any) -> str:
    """Normalize and validate the BIRD router id."""
    text = str(value or DEFAULT_ROUTER_ID).strip()
    try:
        ipaddress.IPv4Address(text)
    except ipaddress.AddressValueError as exc:
        raise HTTPException(status_code=400, detail="router_id must be an IPv4 address.") from exc
    return text


def parse_global_settings(text: str) -> dict[str, Any]:
    """Extract managed global settings from a BIRD configuration file."""
    settings = default_global_settings()
    router_match = re.search(r"^\s*router\s+id\s+([0-9.]+)\s*;", text, re.MULTILINE)
    log_match = re.search(r"^\s*log\s+syslog\s+(all|off)\s*;", text, re.MULTILINE)
    device_match = re.search(r"protocol\s+device\s*\{(?P<body>.*?)\}", text, re.DOTALL)
    kernel_match = re.search(r"protocol\s+kernel\s*\{(?P<body>.*?)\}", text, re.DOTALL)

    if router_match:
        settings["router_id"] = router_match.group(1)
    if log_match:
        settings["log_syslog"] = log_match.group(1) == "all"
    if device_match:
        scan_match = re.search(r"scan\s+time\s+(\d+)\s*;", device_match.group("body"))
        if scan_match:
            settings["device_scan_time"] = int(scan_match.group(1))
    if kernel_match:
        body = kernel_match.group("body")
        settings["kernel_learn"] = bool(re.search(r"^\s*learn\s*;", body, re.MULTILINE))
        settings["kernel_persist"] = bool(re.search(r"^\s*persist\s*;", body, re.MULTILINE))
        scan_match = re.search(r"scan\s+time\s+(\d+)\s*;", body)
        import_match = re.search(r"ipv4\s*\{.*?import\s+(all|none)\s*;", body, re.DOTALL)
        export_match = re.search(r"ipv4\s*\{.*?export\s+(all|none)\s*;", body, re.DOTALL)
        if scan_match:
            settings["kernel_scan_time"] = int(scan_match.group(1))
        if import_match:
            settings["kernel_import"] = import_match.group(1)
        if export_match:
            settings["kernel_export"] = export_match.group(1)
    return settings


def default_global_settings() -> dict[str, Any]:
    """Return default global BIRD daemon settings for the GUI."""
    return {
        "router_id": DEFAULT_ROUTER_ID,
        "log_syslog": True,
        "device_scan_time": 10,
        "kernel_scan_time": 20,
        "kernel_learn": True,
        "kernel_persist": True,
        "kernel_import": "all",
        "kernel_export": "all",
    }


def normalize_global_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate GUI payload for BIRD global settings."""
    return {
        "router_id": router_id_setting(payload.get("router_id")),
        "log_syslog": bool_setting(payload.get("log_syslog", True)),
        "device_scan_time": int_setting(payload.get("device_scan_time"), default=10, minimum=1, maximum=3600, field="device_scan_time"),
        "kernel_scan_time": int_setting(payload.get("kernel_scan_time"), default=20, minimum=1, maximum=3600, field="kernel_scan_time"),
        "kernel_learn": bool_setting(payload.get("kernel_learn")),
        "kernel_persist": bool_setting(payload.get("kernel_persist")),
        "kernel_import": import_export_setting(payload.get("kernel_import"), field="kernel_import"),
        "kernel_export": import_export_setting(payload.get("kernel_export"), field="kernel_export"),
    }


def render_global_config(settings: dict[str, Any]) -> str:
    """Render a managed BIRD global configuration."""
    learn_line = "  learn;\n" if settings["kernel_learn"] else ""
    persist_line = "  persist;\n" if settings["kernel_persist"] else ""
    log_target = "all" if settings["log_syslog"] else "off"
    return f"""# Managed by ArmFirewall Network / Routing Protocols.
router id {settings["router_id"]};
log syslog {log_target};

protocol device {{
  scan time {settings["device_scan_time"]};
}}

protocol kernel {{
{learn_line}{persist_line}  scan time {settings["kernel_scan_time"]};
  ipv4 {{
    import {settings["kernel_import"]};
    export {settings["kernel_export"]};
  }};
}}
"""


def get_global_settings() -> dict[str, Any]:
    """Return current BIRD global daemon settings and status."""
    path = bird_config_path()
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    settings = parse_global_settings(text) if text else default_global_settings()
    return {
        "service": bird_status(),
        "bird_version": bird_version(),
        "config_path": str(path),
        "exists": path.exists(),
        "settings": settings,
        "rendered_config": render_global_config(settings),
    }


def save_global_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist BIRD global daemon settings to the host configuration file."""
    settings = normalize_global_settings(payload)
    path = bird_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_path = path.with_suffix(path.suffix + ".armfw.bak")
        shutil.copy2(path, backup_path)
    path.write_text(render_global_config(settings), encoding="utf-8")
    return get_global_settings() | {"saved": True}
