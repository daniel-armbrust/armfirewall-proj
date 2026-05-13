from __future__ import annotations

import ipaddress
import json
import fcntl
import re
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
from web.constants import TEMPLATE_DIR


MTR_LOCK_PATH = Path("/tmp/armfirewall-mtr.lock")
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
    }


def render_mtr(request: Request) -> HTMLResponse:
    """Render the Tools / MTR page."""
    return templates.TemplateResponse(
        request,
        "tools/mtr.html",
        context=page_context(request, "MTR"),
    )


def list_interfaces() -> list[dict[str, Any]]:
    """Return interfaces that can be used as mtr source devices."""
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
    """Validate a mtr target as an IP address or safe DNS name."""
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


def validate_float(value: Any, default: float, minimum: float, maximum: float, name: str) -> float:
    """Return a floating point value constrained to a safe range."""
    if value in (None, ""):
        return default
    try:
        number = float(value)
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
    """Return the requested mtr probe protocol."""
    protocol = str(value or "icmp").strip().lower()
    if protocol not in {"udp", "icmp", "tcp"}:
        raise ValueError("Invalid mtr protocol.")
    return protocol


def validate_port(value: Any) -> int | None:
    """Return a TCP or UDP destination port when provided."""
    if value in (None, ""):
        return None
    return validate_int(value, 0, 1, 65535, "Port")


def validate_interface(value: Any) -> str:
    """Return a configured interface name or an empty string."""
    iface = str(value or "").strip()
    if not iface:
        return ""
    allowed = {item["name"] for item in list_interfaces()}
    if iface not in allowed:
        raise ValueError("Invalid interface.")
    return iface


def mtr_binary() -> str:
    """Return the mtr binary path or fail clearly."""
    binary = shutil.which("mtr")
    if not binary:
        raise ValueError("mtr command was not found.")
    return binary


def build_mtr_command(payload: dict[str, Any]) -> list[str]:
    """Build a safe mtr command without shell interpolation."""
    target = validate_target(payload.get("target"))
    max_hops = validate_int(payload.get("max_hops"), 30, 1, 64, "Max hops")
    timeout = validate_int(payload.get("timeout"), 3, 1, 10, "Timeout")
    interval = validate_float(payload.get("interval"), 1.0, 0.2, 10.0, "Interval")
    family = validate_family(payload.get("family"))
    protocol = validate_protocol(payload.get("protocol"))
    port = validate_port(payload.get("port"))
    iface = validate_interface(payload.get("iface"))
    command = [
        mtr_binary(),
        "--raw",
        "--no-dns",
        "--max-ttl",
        str(max_hops),
        "--timeout",
        str(timeout),
        "--interval",
        str(interval),
    ]

    if family == "ipv4":
        command.append("-4")
    elif family == "ipv6":
        command.append("-6")

    if protocol == "udp":
        command.append("--udp")
    elif protocol == "tcp":
        command.append("--tcp")

    if port is not None and protocol in {"udp", "tcp"}:
        command.extend(["--port", str(port)])

    if iface:
        command.extend(["--interface", iface])

    command.append(target)
    return command


def stream_event(event: str, payload: dict[str, Any]) -> str:
    """Serialize one server-sent event for streaming mtr output."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def new_hop_stats(host: str = "-") -> dict[str, Any]:
    """Create an empty MTR statistics record for one hop."""
    return {
        "host": host,
        "sent": 0,
        "recv": 0,
        "last": None,
        "best": None,
        "worst": None,
        "total": 0.0,
    }


def update_latency_stats(stats: dict[str, Any], latency_ms: float, max_count: int) -> None:
    """Update one hop statistics record with a received latency."""
    if int(stats["recv"]) >= max_count:
        return
    stats["recv"] += 1
    stats["last"] = latency_ms
    stats["total"] += latency_ms
    stats["best"] = latency_ms if stats["best"] is None else min(stats["best"], latency_ms)
    stats["worst"] = latency_ms if stats["worst"] is None else max(stats["worst"], latency_ms)


def format_latency(value: Any) -> str:
    """Format a latency value for the MTR table."""
    if value is None:
        return "-"
    return f"{float(value):.3f}"


def render_mtr_snapshot(hops: dict[int, dict[str, Any]]) -> str:
    """Render current MTR hop statistics as a stable text table."""
    lines = [
        "HOP HOST                                      LOSS% SENT RECV LAST(ms) AVG(ms) BEST(ms) WORST(ms)",
        "--- ----------------------------------------- ----- ---- ---- -------- ------- -------- ---------",
    ]

    for hop in sorted(hops):
        stats = hops[hop]
        sent = int(stats["sent"])
        recv = int(stats["recv"])
        loss = ((sent - recv) / sent * 100) if sent else 0.0
        avg = (float(stats["total"]) / recv) if recv else None
        host = str(stats["host"] or "-")[:41]
        lines.append(
            f"{hop + 1:>3} {host:<41} {loss:>5.1f} {sent:>4} {recv:>4} "
            f"{format_latency(stats['last']):>8} {format_latency(avg):>7} "
            f"{format_latency(stats['best']):>8} {format_latency(stats['worst']):>9}"
        )

    return "\n".join(lines)


def update_raw_mtr_stats(line: str, hops: dict[int, dict[str, Any]], max_count: int) -> bool:
    """Apply one raw mtr event to the live hop statistics."""
    parts = line.strip().split()
    if not parts:
        return False

    event = parts[0]

    try:
        if len(parts) >= 2:
            hop = int(parts[1])
        else:
            hop = 0
    except ValueError:
        return False

    stats = hops.setdefault(hop, new_hop_stats())

    if event == "h" and len(parts) >= 3:
        stats["host"] = parts[2]
        return True

    if event == "x" and len(parts) >= 3:
        if int(stats["sent"]) < max_count:
            stats["sent"] += 1
        return True

    if event == "p" and len(parts) >= 4:
        latency_ms = int(parts[2]) / 1000
        update_latency_stats(stats, latency_ms, max_count)
        return True

    if event == "d" and len(parts) >= 3:
        return True

    return False


def stream_mtr(payload: dict[str, Any]):
    """Execute mtr and yield server-sent events as output arrives."""
    lock_file = MTR_LOCK_PATH.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        yield stream_event("busy", {"message": "MTR is already running."})
        yield stream_event("done", {"returncode": 1, "ok": False})
        return

    try:
        command = build_mtr_command(payload)
        timeout = validate_int(payload.get("timeout"), 3, 1, 10, "Timeout")
        count = validate_int(payload.get("count"), 10, 1, 100, "Count")
        interval = validate_float(payload.get("interval"), 1.0, 0.2, 10.0, "Interval")
        deadline = int((count * (interval + timeout)) + 20)
        started_at = time.monotonic()
        stop_after = started_at + max(2.0, (count * interval) + timeout + 1)
        hops: dict[int, dict[str, Any]] = {}
        sent_first_hop = 0
        completed_by_count = False

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
                raw_line = line.rstrip("\n")
                parts = raw_line.split()
                if len(parts) >= 2 and parts[0] == "x" and parts[1] == "0":
                    sent_first_hop += 1

                if update_raw_mtr_stats(raw_line, hops, count):
                    yield stream_event("snapshot", {"text": render_mtr_snapshot(hops)})

                if sent_first_hop >= count and time.monotonic() >= stop_after:
                    completed_by_count = True
                    process.terminate()
                    break

                if time.monotonic() - started_at > deadline:
                    process.kill()
                    yield stream_event("line", {"line": "MTR command timed out."})
                    break

            returncode = process.wait(timeout=deadline)
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = process.wait()
            yield stream_event("line", {"line": "MTR command timed out."})
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        yield stream_event("done", {"returncode": returncode, "ok": returncode == 0 or completed_by_count})
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
