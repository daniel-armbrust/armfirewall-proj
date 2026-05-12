"""Interface graph generation helpers."""

from __future__ import annotations

from pathlib import Path

from core.process import run_command

from ..constants import RRD_DIR, RRD_IMG_DIR
from ..periods import GRAPH_PERIODS, period_image_path
from ..rrd import rrd_safe_name
from .constants import MONITORIX_GRAPH_COLORS


def rrd_path_for_iface(iface_name: str) -> Path:
    """Return the RRD path for one interface."""
    return RRD_DIR / f"{rrd_safe_name(iface_name)}.rrd"


def image_path_for_iface(iface_name: str, suffix: str) -> Path:
    """Return one graph image path for an interface."""
    return RRD_IMG_DIR / f"{rrd_safe_name(iface_name)}-{suffix}.png"


def graph_traffic(rrdtool: str, iface_name: str, rrd_path: Path) -> None:
    """Generate traffic bandwidth graphs for all standard periods."""
    base_path = image_path_for_iface(iface_name, "traffic")
    
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
                f"{iface_name} traffic - {period_label}",
                "--vertical-label",
                "bytes/s",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:rx={rrd_path}:rx_bytes:AVERAGE",
                f"DEF:tx={rrd_path}:tx_bytes:AVERAGE",
                "CDEF:B_in=rx",
                "CDEF:B_out=tx",
                "CDEF:K_in=B_in,1024,/",
                "CDEF:K_out=B_out,1024,/",
                "AREA:B_in#44EE44:KB/s Input",
                "GPRINT:K_in:LAST:     Current\\: %5.0lf",
                "GPRINT:K_in:AVERAGE: Average\\: %5.0lf",
                "GPRINT:K_in:MIN:    Min\\: %5.0lf",
                "GPRINT:K_in:MAX:    Max\\: %5.0lf\\n",
                "AREA:B_out#4444EE:KB/s Output",
                "GPRINT:K_out:LAST:    Current\\: %5.0lf",
                "GPRINT:K_out:AVERAGE: Average\\: %5.0lf",
                "GPRINT:K_out:MIN:    Min\\: %5.0lf",
                "GPRINT:K_out:MAX:    Max\\: %5.0lf\\n",
                "AREA:B_out#4444EE:",
                "AREA:B_in#44EE44:",
                "LINE1:B_out#0000EE",
                "LINE1:B_in#00EE00",
            ]
        )


def graph_packets(rrdtool: str, iface_name: str, rrd_path: Path) -> None:
    """Generate packets-per-second graphs for all standard periods."""
    base_path = image_path_for_iface(iface_name, "packets")
    
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
                f"{iface_name} packets - {period_label}",
                "--vertical-label",
                "Packets/s",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:rx={rrd_path}:rx_packets:AVERAGE",
                f"DEF:tx={rrd_path}:tx_packets:AVERAGE",
                "CDEF:p_in=rx",
                "CDEF:p_out=tx",
                "AREA:p_in#44EE44:Input",
                "AREA:p_out#4444EE:Output",
                "AREA:p_out#4444EE:",
                "AREA:p_in#44EE44:",
                "LINE1:p_out#0000EE",
                "LINE1:p_in#00EE00",
            ]
        )


def graph_errors(rrdtool: str, iface_name: str, rrd_path: Path) -> None:
    """Generate errors and drops graphs for all standard periods."""
    base_path = image_path_for_iface(iface_name, "errors")
    
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
                f"{iface_name} errors - {period_label}",
                "--vertical-label",
                "Errors/s",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:rxe={rrd_path}:rx_errors:AVERAGE",
                f"DEF:txe={rrd_path}:tx_errors:AVERAGE",
                "CDEF:e_in=rxe",
                "CDEF:e_out=txe",
                "AREA:e_in#44EE44:Input",
                "AREA:e_out#4444EE:Output",
                "AREA:e_out#4444EE:",
                "AREA:e_in#44EE44:",
                "LINE1:e_out#0000EE",
                "LINE1:e_in#00EE00",
            ]
        )


def generate_graphs(rrdtool: str, iface_name: str) -> None:
    """Generate all graph images for one interface RRD."""
    rrd_path = rrd_path_for_iface(iface_name)
    
    graph_traffic(rrdtool, iface_name, rrd_path)
    graph_packets(rrdtool, iface_name, rrd_path)
    graph_errors(rrdtool, iface_name, rrd_path)
