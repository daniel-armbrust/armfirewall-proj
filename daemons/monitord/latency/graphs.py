"""Latency graph generation helpers."""

from __future__ import annotations

from pathlib import Path

from core.process import run_command

from ..constants import RRD_IMG_DIR
from ..periods import GRAPH_PERIODS, period_image_path
from ..rrd import rrd_safe_name
from .constants import MONITORIX_GRAPH_COLORS
from .models import LatencyTarget


def image_path_for_target(target: LatencyTarget, suffix: str) -> Path:
    """Return one graph image path for a latency target."""
    return RRD_IMG_DIR / f"latency-{rrd_safe_name(target.name, default='target')}-{suffix}.png"


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
                "--upper-limit",
                "200",
                "--lower-limit",
                "0",
                "--rigid",
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
                "--rigid",
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
