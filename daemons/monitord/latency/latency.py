#!/usr/bin/env python3
"""Latency monitoring collector based on ping probes."""

from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..constants import COLLECT_INTERVAL_SECONDS, RRD_DIR, RRD_IMG_DIR
from ..periods import GRAPH_PERIODS, period_image_path
from core import db
from core import log as logger

from .constants import LATENCY_DB_PATH, LATENCY_DS, LOG_SOURCE, MONITORIX_GRAPH_COLORS
from .models import LatencyTarget, PingResult


def run_command(command: list[str]) -> None:
    """Run one external command and raise a useful error on failure."""
    subprocess.run(command, check=True, text=True, capture_output=True)


def command_output(command: list[str]) -> str:
    """Run one command and return stdout when it succeeds."""
    result = subprocess.run(command, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        return ""
    return result.stdout


def positive_int(value: Any, default: int) -> int:
    """Return a positive integer from database values."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return parsed if parsed > 0 else default


def rrd_data_sources(rrdtool: str, rrd_path: Path) -> set[str]:
    """Return the data source names currently stored in an RRD file."""
    result = subprocess.run([rrdtool, "info", str(rrd_path)], check=True, text=True, capture_output=True)
    sources: set[str] = set()
    for line in result.stdout.splitlines():
        if not line.startswith("ds["):
            continue
        sources.add(line.split("[", 1)[1].split("]", 1)[0])
    return sources


def sanitize_target_name(name: str) -> str:
    """Return a filesystem-safe target name."""
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    return sanitized.strip("_") or "target"


def configured_target_name(iface: str, address: str) -> str:
    """Return the graph-safe target name used by the web GUI."""
    return sanitize_target_name(f"{iface}-{address}")


def safe_rrd_value(value: float | None) -> str:
    """Format a value for RRD update syntax."""
    if value is None:
        return "U"
    return f"{value:.2f}"


def latency_targets() -> list[LatencyTarget]:
    """Return enabled latency monitoring targets from latency.db."""
    if not LATENCY_DB_PATH.exists():
        logger.error(f"Latency database was not found: {LATENCY_DB_PATH}", source=LOG_SOURCE)
        return []

    targets: list[LatencyTarget] = []
    seen: set[tuple[str, str]] = set()
    try:
        rows = db.fetch_all(
            """
            SELECT iface, target, count, timeout
            FROM latency_targets
            WHERE enabled = 1
            ORDER BY iface, target
            """,
            db_path=LATENCY_DB_PATH,
        )
    except db.DatabaseError as exc:
        logger.error(f"Could not read latency targets from {LATENCY_DB_PATH}: {exc}", source=LOG_SOURCE)
        return []

    for row in rows:
        iface = str(row.get("iface") or "").strip()
        address = str(row.get("target") or "").strip()
        if not iface or not address:
            continue

        key = (address, iface)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            LatencyTarget(
                name=configured_target_name(iface, address),
                address=address,
                iface=iface,
                description=f"Configured latency target {address} via {iface}",
                packet_count=positive_int(row.get("count"), 3),
                timeout_seconds=positive_int(row.get("timeout"), 3),
            )
        )
    return targets


def is_ipv6_address(address: str) -> bool:
    """Return whether the target address is IPv6."""
    try:
        return isinstance(ipaddress.ip_address(address), ipaddress.IPv6Address)
    except ValueError:
        return ":" in address


def parse_ping_output(output: str) -> PingResult:
    """Parse packet loss and RTT values from ping output."""
    loss_match = re.search(r"(\d+(?:\.\d+)?)%\s+packet loss", output)
    loss_pct = float(loss_match.group(1)) if loss_match else 100.0

    rtt_match = re.search(r"=\s*([\d.]+)/([\d.]+)/([\d.]+)/", output)
    if not rtt_match:
        return PingResult(min_ms=None, avg_ms=None, max_ms=None, loss_pct=loss_pct)

    return PingResult(
        min_ms=float(rtt_match.group(1)),
        avg_ms=float(rtt_match.group(2)),
        max_ms=float(rtt_match.group(3)),
        loss_pct=loss_pct,
    )


def ping_target(target: LatencyTarget) -> PingResult:
    """Execute ping and return latency values for one target."""
    ping_path = shutil.which("ping")
    if not ping_path:
        raise RuntimeError("ping command was not found.")

    args = [ping_path, "-q", "-n", "-c", str(target.packet_count), "-W", str(target.timeout_seconds)]
    args.append("-6" if is_ipv6_address(target.address) else "-4")
    if target.iface:
        args.extend(["-I", target.iface])
    args.append(target.address)

    result = subprocess.run(
        args,
        check=False,
        text=True,
        capture_output=True,
        timeout=max(target.packet_count * target.timeout_seconds + 2, 5),
    )
    output = f"{result.stdout}\n{result.stderr}"
    return parse_ping_output(output)


def rrd_path_for_target(target: LatencyTarget) -> Path:
    """Return the RRD path for one latency target."""
    return RRD_DIR / f"latency-{sanitize_target_name(target.name)}.rrd"


def image_path_for_target(target: LatencyTarget, suffix: str) -> Path:
    """Return one graph image path for a latency target."""
    return RRD_IMG_DIR / f"latency-{sanitize_target_name(target.name)}-{suffix}.png"


def ensure_rrd(rrdtool: str, target: LatencyTarget) -> Path:
    """Create one latency RRD file when needed."""
    rrd_path = rrd_path_for_target(target)
    if rrd_path.exists() and rrd_data_sources(rrdtool, rrd_path) != LATENCY_DS:
        rrd_path.unlink()

    if rrd_path.exists():
        return rrd_path

    heartbeat = max(COLLECT_INTERVAL_SECONDS * 3, 120)
    run_command(
        [
            rrdtool,
            "create",
            str(rrd_path),
            "--step",
            str(COLLECT_INTERVAL_SECONDS),
            f"DS:min:GAUGE:{heartbeat}:0:U",
            f"DS:avg:GAUGE:{heartbeat}:0:U",
            f"DS:max:GAUGE:{heartbeat}:0:U",
            f"DS:loss:GAUGE:{heartbeat}:0:100",
            "RRA:AVERAGE:0.5:1:8640",
            "RRA:AVERAGE:0.5:6:10080",
            "RRA:AVERAGE:0.5:30:1488",
            "RRA:MIN:0.5:1:8640",
            "RRA:MIN:0.5:6:10080",
            "RRA:MIN:0.5:30:1488",
            "RRA:MAX:0.5:1:8640",
            "RRA:MAX:0.5:6:10080",
            "RRA:MAX:0.5:30:1488",
            "RRA:LAST:0.5:1:8640",
            "RRA:LAST:0.5:6:10080",
            "RRA:LAST:0.5:30:1488",
        ]
    )
    logger.info(f"Created latency RRD file for {target.name}: {rrd_path}", source=LOG_SOURCE)
    return rrd_path


def update_rrd(rrdtool: str, target: LatencyTarget, result: PingResult) -> Path:
    """Update one latency RRD with the latest ping result."""
    rrd_path = ensure_rrd(rrdtool, target)
    update_value = (
        f"N:{safe_rrd_value(result.min_ms)}:{safe_rrd_value(result.avg_ms)}:"
        f"{safe_rrd_value(result.max_ms)}:{safe_rrd_value(result.loss_pct)}"
    )
    run_command([rrdtool, "update", str(rrd_path), update_value])
    return rrd_path


def graph_latency(rrdtool: str, target: LatencyTarget, rrd_path: Path) -> None:
    """Generate latency graphs for all standard periods."""
    base_path = image_path_for_target(target, "latency")
    title = f"{target.name} latency ({target.address})"
    for period_name, period_label, period_start in GRAPH_PERIODS:
        run_command(
            [
                rrdtool,
                "graph",
                str(period_image_path(base_path, period_name)),
                "--imgformat",
                "PNG",
                "--start",
                period_start,
                "--width",
                "800",
                "--height",
                "300",
                "--title",
                f"{title} - {period_label}",
                "--vertical-label",
                "Milliseconds",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:min={rrd_path}:min:AVERAGE",
                f"DEF:avg={rrd_path}:avg:AVERAGE",
                f"DEF:max={rrd_path}:max:AVERAGE",
                "LINE1:min#44EE44:Min",
                "GPRINT:min:LAST: Current\\: %5.2lf ms",
                "GPRINT:min:MIN: Min\\: %5.2lf",
                "GPRINT:min:MAX: Max\\: %5.2lf\\n",
                "LINE2:avg#EEEE44:Avg",
                "GPRINT:avg:LAST: Current\\: %5.2lf ms",
                "GPRINT:avg:MIN: Min\\: %5.2lf",
                "GPRINT:avg:MAX: Max\\: %5.2lf\\n",
                "LINE1:max#EE4444:Max",
                "GPRINT:max:LAST: Current\\: %5.2lf ms",
                "GPRINT:max:MIN: Min\\: %5.2lf",
                "GPRINT:max:MAX: Max\\: %5.2lf\\n",
            ]
        )


def graph_loss(rrdtool: str, target: LatencyTarget, rrd_path: Path) -> None:
    """Generate packet loss graphs for all standard periods."""
    base_path = image_path_for_target(target, "loss")
    title = f"{target.name} packet loss ({target.address})"
    for period_name, period_label, period_start in GRAPH_PERIODS:
        run_command(
            [
                rrdtool,
                "graph",
                str(period_image_path(base_path, period_name)),
                "--imgformat",
                "PNG",
                "--start",
                period_start,
                "--width",
                "800",
                "--height",
                "300",
                "--title",
                f"{title} - {period_label}",
                "--vertical-label",
                "Percent (%)",
                "--upper-limit",
                "100",
                "--lower-limit",
                "0",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:loss={rrd_path}:loss:AVERAGE",
                "AREA:loss#EE4444:Packet loss",
                "GPRINT:loss:LAST: Current\\: %5.2lf%%",
                "GPRINT:loss:MIN: Min\\: %5.2lf%%",
                "GPRINT:loss:MAX: Max\\: %5.2lf%%\\n",
                "LINE2:loss#CC0000",
            ]
        )


def generate_graphs(rrdtool: str, target: LatencyTarget, rrd_path: Path) -> None:
    """Generate all latency graph images for one target."""
    graph_latency(rrdtool, target, rrd_path)
    graph_loss(rrdtool, target, rrd_path)


class LatencyMonitor:
    """Collect ping latency metrics and maintain their RRD graphs."""

    name = "latency"

    def __init__(self, rrdtool: str) -> None:
        """Prepare the latency monitor dependencies."""
        self.rrdtool = rrdtool

    def collect(self) -> None:
        """Run one latency monitoring cycle."""
        targets = latency_targets()
        for target in targets:
            try:
                result = ping_target(target)
                rrd_path = update_rrd(self.rrdtool, target, result)
                generate_graphs(self.rrdtool, target, rrd_path)
            except Exception as exc:  # noqa: BLE001 - one target must not stop the collector.
                logger.error(f"Latency probe failed for {target.name} ({target.address}): {exc}", source=LOG_SOURCE)
        logger.info(f"Monitored {len(targets)} latency targets into {RRD_DIR}.", source=LOG_SOURCE)
