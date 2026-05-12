from __future__ import annotations

import fcntl
import ipaddress
import json
import re
import select
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web import auth
from core import db
from core.constants import IFACE_DB_PATH


ROOT_DIR = Path(__file__).resolve().parents[2]
PACKET_CAPTURE_LOCK_PATH = Path("/tmp/armfirewall-packet-capture.lock")
templates = Jinja2Templates(directory=[ROOT_DIR / "web" / "templates", ROOT_DIR / "templates"])
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
PACKET_LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\S+\s+")
ANY_PACKET_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\S+\s+(\S+)\s+(In|Out)\s+")


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for Tools pages."""
    current_user = auth.get_current_user(request) or {}
    return {
        "request": request,
        "title": title,
        "user_name": current_user.get("username", "admin"),
        "current_path": request.url.path,
    }


def render_packet_capture(request: Request) -> HTMLResponse:
    """Render the Tools / Packet Capture page."""
    return templates.TemplateResponse(
        request,
        "tools/packet_capture.html",
        context=page_context(request, "Packet Capture"),
    )


def list_interfaces() -> list[dict[str, Any]]:
    """Return interfaces that can be used for packet capture."""
    return db.fetch_all(
        """
        SELECT name, role, description, is_actived
          FROM ifaces
         ORDER BY
            CASE role
                WHEN 'LAN' THEN 1
                WHEN 'WAN' THEN 2
                ELSE 3
            END,
            name
        """,
        db_path=IFACE_DB_PATH,
    )


def validate_int(value: Any, default: int, minimum: int, maximum: int, name: str) -> int:
    """Return an integer constrained to a safe range."""
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return number


def validate_bool(value: Any) -> bool:
    """Return a boolean value from browser payload data."""
    return value in {True, "true", "1", 1, "on", "yes"}


def validate_optional_interface(value: Any) -> str:
    """Return a configured interface name or an empty string."""
    iface = str(value or "").strip()
    if not iface:
        return ""
    allowed = {item["name"] for item in list_interfaces()}
    if iface not in allowed:
        raise ValueError("Invalid interface.")
    return iface


def validate_interface(value: Any) -> str:
    """Return a configured interface name for packet capture."""
    return validate_optional_interface(value)


def selected_capture_interfaces(payload: dict[str, Any]) -> tuple[str, str]:
    """Return selected inbound and outbound capture interfaces."""
    legacy_iface = str(payload.get("iface") or "").strip()
    iface_in = str(payload.get("iface_in") or legacy_iface or "").strip()
    iface_out = str(payload.get("iface_out") or "").strip()

    if iface_in:
        iface_in = validate_optional_interface(iface_in)
    if iface_out:
        iface_out = validate_optional_interface(iface_out)

    return iface_in, iface_out


def validate_protocol(value: Any) -> str:
    """Return a supported tcpdump protocol filter."""
    protocol = str(value or "any").strip().lower()
    if protocol not in {"any", "tcp", "udp", "icmp", "icmp6", "arp"}:
        raise ValueError("Invalid protocol.")
    return protocol


def validate_direction(value: Any, name: str) -> str:
    """Return a supported tcpdump direction qualifier."""
    direction = str(value or "any").strip().lower()
    if direction not in {"any", "src", "dst"}:
        raise ValueError(f"Invalid {name} direction.")
    return direction


def validate_host(value: Any) -> str:
    """Validate a tcpdump host filter value."""
    host = str(value or "").strip()
    if not host:
        return ""

    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass

    if not HOST_RE.fullmatch(host) or ".." in host or host.startswith(("-", ".")) or host.endswith("."):
        raise ValueError("Invalid host filter.")
    return host


def tcpdump_binary() -> str:
    """Return the tcpdump binary path or fail clearly."""
    binary = shutil.which("tcpdump")
    if not binary:
        raise ValueError("tcpdump command was not found.")
    return binary


def build_capture_filter(payload: dict[str, Any]) -> list[str]:
    """Build a structured tcpdump capture filter without shell interpolation."""
    parts: list[str] = []
    protocol = validate_protocol(payload.get("protocol"))
    host = validate_host(payload.get("host"))
    host_direction = validate_direction(payload.get("host_direction"), "host")
    port = validate_int(payload.get("port"), 0, 0, 65535, "Port")
    port_direction = validate_direction(payload.get("port_direction"), "port")

    if protocol != "any":
        parts.append(protocol)

    if host:
        if host_direction != "any":
            parts.append(host_direction)
        parts.extend(["host", host])

    if port:
        if port_direction != "any":
            parts.append(port_direction)
        parts.extend(["port", str(port)])

    return parts


def build_packet_capture_command(payload: dict[str, Any]) -> list[str]:
    """Build a safe tcpdump command without shell interpolation."""
    iface_in, iface_out = selected_capture_interfaces(payload)
    snaplen = validate_int(payload.get("snaplen"), 128, 64, 262144, "Snaplen")
    promiscuous = validate_bool(payload.get("promiscuous"))
    if iface_in and iface_out and iface_in != iface_out:
        capture_iface = "any"
        direction_args: list[str] = []
    else:
        capture_iface = iface_in or iface_out or "any"
        direction_args = []
        if iface_in and not iface_out:
            direction_args = ["-Q", "in"]
        elif iface_out and not iface_in:
            direction_args = ["-Q", "out"]

    command = [
        tcpdump_binary(),
        "-l",
        "-n",
        "-tttt",
        "-i",
        capture_iface,
        "-s",
        str(snaplen),
    ]
    command.extend(direction_args)

    if not promiscuous:
        command.append("-p")

    command.extend(build_capture_filter(payload))
    return command


def acquire_capture_lock():
    """Acquire the global packet capture execution lock or fail fast."""
    lock_file = PACKET_CAPTURE_LOCK_PATH.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_file.close()
        raise ValueError("Packet capture is already running.") from exc
    return lock_file


def release_capture_lock(lock_file) -> None:
    """Release the global packet capture execution lock."""
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    lock_file.close()


def stream_event(event: str, payload: dict[str, Any]) -> str:
    """Serialize one server-sent event for streaming tcpdump output."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def should_emit_capture_line(line: str, iface_in: str, iface_out: str) -> bool:
    """Return whether one tcpdump line matches selected IN/OUT interfaces."""
    if not iface_in or not iface_out or iface_in == iface_out:
        return True

    match = ANY_PACKET_RE.match(line)
    if not match:
        return True

    iface, direction = match.groups()
    return (iface == iface_in and direction == "In") or (iface == iface_out and direction == "Out")


def is_packet_line(line: str) -> bool:
    """Return whether one tcpdump output line looks like a packet."""
    return bool(PACKET_LINE_RE.match(line))


def stream_packet_capture(payload: dict[str, Any]):
    """Execute tcpdump and yield server-sent events as packets arrive."""
    iface_in, iface_out = selected_capture_interfaces(payload)
    command = build_packet_capture_command(payload)
    count = validate_int(payload.get("count"), 100, 1, 10000, "Count")
    timeout = validate_int(payload.get("timeout"), 5, 1, 3600, "Timeout")

    try:
        lock_file = acquire_capture_lock()
    except ValueError:
        yield stream_event("busy", {"message": "Packet capture is already running."})
        yield stream_event("done", {"returncode": 1, "ok": False})
        return

    try:
        yield stream_event("start", {"command": " ".join(command)})

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        returncode = 1

        assert process.stdout is not None
        deadline = time.monotonic() + timeout
        timed_out = False
        count_reached = False
        emitted_packets = 0

        while process.poll() is None:
            if emitted_packets >= count:
                count_reached = True
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            ready, _, _ = select.select([process.stdout], [], [], 0.5)
            if not ready:
                continue
            line = process.stdout.readline()
            if not line:
                break
            clean_line = line.rstrip("\n")
            if should_emit_capture_line(clean_line, iface_in, iface_out):
                yield stream_event("line", {"line": clean_line})
                if is_packet_line(clean_line):
                    emitted_packets += 1

        if timed_out:
            process.terminate()
            try:
                returncode = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = process.wait()
            yield stream_event("line", {"line": "Packet capture timed out."})
        elif count_reached and process.poll() is None:
            process.terminate()
            try:
                returncode = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = process.wait()
        else:
            returncode = process.wait(timeout=2)

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        yield stream_event("done", {"returncode": returncode, "ok": returncode == 0 or count_reached})
    finally:
        release_capture_lock(lock_file)
