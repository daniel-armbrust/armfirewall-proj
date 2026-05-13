from __future__ import annotations

import fcntl
import ipaddress
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web import auth
from core import db
from core.constants import IFACE_DB_PATH
from web.constants import TEMPLATE_DIR
from web.context import menu_context


TRACEROUTE_LOCK_PATH = Path("/tmp/armfirewall-traceroute.lock")
templates = Jinja2Templates(directory=TEMPLATE_DIR)
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for Tools pages."""
    current_user = auth.get_current_user(request) or {}
    return {
        "request": request,
        "title": title,
        "user_name": current_user.get("username", "admin"),
        "current_path": request.url.path,
        "menu": menu_context(),
    }


def render_traceroute(request: Request) -> HTMLResponse:
    """Render the Tools / Traceroute page."""
    return templates.TemplateResponse(
        request,
        "tools/traceroute.html",
        context=page_context(request, "Traceroute"),
    )


def list_interfaces() -> list[dict[str, Any]]:
    """Return interfaces that can be used as traceroute source devices."""
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


def validate_target(value: Any) -> str:
    """Validate a traceroute target as an IP address or safe DNS name."""
    target = str(value or "").strip()
    if not target:
        raise ValueError("Target is required.")

    try:
        return str(ipaddress.ip_address(target))
    except ValueError:
        pass

    if not HOST_RE.fullmatch(target) or ".." in target or target.startswith(("-", ".")) or target.endswith("."):
        raise ValueError("Invalid target.")
    return target


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


def validate_family(value: Any) -> str:
    """Return the requested address family."""
    family = str(value or "auto").strip().lower()
    if family not in {"auto", "ipv4", "ipv6"}:
        raise ValueError("Invalid address family.")
    return family


def validate_protocol(value: Any) -> str:
    """Return the requested traceroute probe protocol."""
    protocol = str(value or "udp").strip().lower()
    if protocol not in {"udp", "icmp", "tcp"}:
        raise ValueError("Invalid traceroute protocol.")
    return protocol


def validate_interface(value: Any) -> str:
    """Return a configured interface name or an empty string."""
    iface = str(value or "").strip()
    if not iface:
        return ""
    allowed = {item["name"] for item in list_interfaces()}
    if iface not in allowed:
        raise ValueError("Invalid interface.")
    return iface


def traceroute_binary() -> str:
    """Return the traceroute binary path or fail clearly."""
    binary = shutil.which("traceroute")
    if not binary:
        raise ValueError("traceroute command was not found.")
    return binary


def build_traceroute_command(payload: dict[str, Any]) -> list[str]:
    """Build a safe traceroute command without shell interpolation."""
    target = validate_target(payload.get("target"))
    max_hops = validate_int(payload.get("max_hops"), 30, 1, 64, "Max hops")
    timeout = validate_int(payload.get("timeout"), 3, 1, 10, "Timeout")
    probes = validate_int(payload.get("probes"), 3, 1, 5, "Probes")
    family = validate_family(payload.get("family"))
    protocol = validate_protocol(payload.get("protocol"))
    iface = validate_interface(payload.get("iface"))
    command = [traceroute_binary(), "-n", "-m", str(max_hops), "-w", str(timeout), "-q", str(probes)]

    if family == "ipv4":
        command.append("-4")
    elif family == "ipv6":
        command.append("-6")

    if protocol == "icmp":
        command.append("-I")
    elif protocol == "tcp":
        command.append("-T")

    if iface:
        command.extend(["-i", iface])

    command.append(target)
    return command


def acquire_traceroute_lock():
    """Acquire the global traceroute execution lock or fail fast."""
    lock_file = TRACEROUTE_LOCK_PATH.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_file.close()
        raise ValueError("Traceroute is already running.") from exc
    return lock_file


def release_traceroute_lock(lock_file) -> None:
    """Release the global traceroute execution lock."""
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    lock_file.close()


def stream_event(event: str, payload: dict[str, Any]) -> str:
    """Serialize one server-sent event for streaming traceroute output."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def stream_traceroute(payload: dict[str, Any]):
    """Execute traceroute and yield server-sent events as output arrives."""
    command = build_traceroute_command(payload)
    max_hops = validate_int(payload.get("max_hops"), 30, 1, 64, "Max hops")
    timeout = validate_int(payload.get("timeout"), 3, 1, 10, "Timeout")
    probes = validate_int(payload.get("probes"), 3, 1, 5, "Probes")
    deadline = (max_hops * timeout * probes) + 10

    try:
        lock_file = acquire_traceroute_lock()
    except ValueError:
        yield stream_event("busy", {"message": "Traceroute is already running."})
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

        try:
            assert process.stdout is not None
            for line in process.stdout:
                yield stream_event("line", {"line": line.rstrip("\n")})
            returncode = process.wait(timeout=deadline)
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = process.wait()
            yield stream_event("line", {"line": "Traceroute command timed out."})
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        yield stream_event("done", {"returncode": returncode, "ok": returncode == 0})
    finally:
        release_traceroute_lock(lock_file)
