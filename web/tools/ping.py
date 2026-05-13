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


PING_LOCK_PATH = Path("/tmp/armfirewall-ping.lock")
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


def render_ping(request: Request) -> HTMLResponse:
    """Render the Tools / Ping page."""
    return templates.TemplateResponse(
        request,
        "tools/ping.html",
        context=page_context(request, "Ping"),
    )


def list_interfaces() -> list[dict[str, Any]]:
    """Return interfaces that can be used as ping source devices."""
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
    """Validate a ping target as an IP address or safe DNS name."""
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


def validate_interface(value: Any) -> str:
    """Return a configured interface name or an empty string."""
    iface = str(value or "").strip()
    if not iface:
        return ""
    allowed = {item["name"] for item in list_interfaces()}
    if iface not in allowed:
        raise ValueError("Invalid interface.")
    return iface


def ping_binary(family: str) -> str:
    """Return the ping binary for the requested address family."""
    if family == "ipv6":
        binary = shutil.which("ping6") or shutil.which("ping")
    else:
        binary = shutil.which("ping")
    if not binary:
        raise ValueError("ping command was not found.")
    return binary


def build_ping_command(payload: dict[str, Any]) -> list[str]:
    """Build a safe ping command without shell interpolation."""
    target = validate_target(payload.get("target"))
    count = validate_int(payload.get("count"), 4, 1, 10, "Count")
    timeout = validate_int(payload.get("timeout"), 3, 1, 10, "Timeout")
    family = validate_family(payload.get("family"))
    iface = validate_interface(payload.get("iface"))
    binary = ping_binary(family)
    command = [binary]

    if family == "ipv4":
        command.append("-4")
    elif family == "ipv6" and Path(binary).name == "ping":
        command.append("-6")

    command.extend(["-c", str(count), "-W", str(timeout)])

    if iface:
        command.extend(["-I", iface])

    command.append(target)
    return command


def acquire_ping_lock():
    """Acquire the global ping execution lock or fail fast."""
    lock_file = PING_LOCK_PATH.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_file.close()
        raise ValueError("Ping is already running.") from exc
    return lock_file


def release_ping_lock(lock_file) -> None:
    """Release the global ping execution lock."""
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    lock_file.close()


def run_ping(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute ping with bounded parameters and return command output."""
    command = build_ping_command(payload)
    timeout = validate_int(payload.get("timeout"), 3, 1, 10, "Timeout")
    count = validate_int(payload.get("count"), 4, 1, 10, "Count")
    lock_file = acquire_ping_lock()
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=(count * timeout) + 5,
            check=False,
        )
    finally:
        release_ping_lock(lock_file)

    output = "\n".join(part for part in [process.stdout.strip(), process.stderr.strip()] if part)
    return {
        "command": " ".join(command),
        "returncode": process.returncode,
        "ok": process.returncode == 0,
        "output": output,
    }


def stream_event(event: str, payload: dict[str, Any]) -> str:
    """Serialize one server-sent event for streaming ping output."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def stream_ping(payload: dict[str, Any]):
    """Execute ping and yield server-sent events as output arrives."""
    command = build_ping_command(payload)
    timeout = validate_int(payload.get("timeout"), 3, 1, 10, "Timeout")
    count = validate_int(payload.get("count"), 4, 1, 10, "Count")
    deadline = (count * timeout) + 5

    try:
        lock_file = acquire_ping_lock()
    except ValueError:
        yield stream_event("busy", {"message": "Ping is already running."})
        yield stream_event("done", {"returncode": 1, "ok": False})
        return

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
        yield stream_event("line", {"line": "Ping command timed out."})
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        release_ping_lock(lock_file)

    yield stream_event("done", {"returncode": returncode, "ok": returncode == 0})
