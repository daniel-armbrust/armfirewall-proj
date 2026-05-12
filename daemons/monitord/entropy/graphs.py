"""Entropy graph generation helpers."""

from __future__ import annotations

from core.process import run_command

from ..constants import RRD_IMG_DIR
from ..periods import GRAPH_PERIODS, period_image_path
from .constants import MONITORIX_GRAPH_COLORS, RRD_PATH


def graph_entropy(rrdtool: str) -> None:
    """Generate kernel entropy graphs for all standard periods."""
    base_path = RRD_IMG_DIR / "entropy-entropy.png"
    
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
                f"Kernel entropy - {period_label}",
                "--vertical-label",
                "Size",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:entropy={RRD_PATH}:entropy_available:AVERAGE",
                "LINE2:entropy#EEEE00:Entropy",
                "GPRINT:entropy:LAST:              Current\\:%5.0lf\\n",
            ]
        )
