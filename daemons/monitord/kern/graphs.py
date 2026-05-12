"""Kernel graph generation helpers."""

from __future__ import annotations

from core.process import run_command

from ..constants import RRD_IMG_DIR
from ..periods import GRAPH_PERIODS, period_image_path
from .constants import MONITORIX_GRAPH_COLORS, RRD_PATH


def graph_cpu(rrdtool: str) -> None:
    """Generate kernel CPU usage graphs for all standard periods."""
    base_path = RRD_IMG_DIR / "kern-cpu.png"
    
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
                f"Kernel usage - {period_label}",
                "--vertical-label",
                "Stacked Percent (%)",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:user={RRD_PATH}:kern_user:AVERAGE",
                f"DEF:nice={RRD_PATH}:kern_nice:AVERAGE",
                f"DEF:sys={RRD_PATH}:kern_sys:AVERAGE",
                f"DEF:iow={RRD_PATH}:kern_iow:AVERAGE",
                f"DEF:irq={RRD_PATH}:kern_irq:AVERAGE",
                f"DEF:sirq={RRD_PATH}:kern_sirq:AVERAGE",
                f"DEF:steal={RRD_PATH}:kern_steal:AVERAGE",
                f"DEF:guest={RRD_PATH}:kern_guest:AVERAGE",
                "CDEF:s_nice=user,nice,+",
                "CDEF:s_sys=s_nice,sys,+",
                "CDEF:s_iow=s_sys,iow,+",
                "CDEF:s_irq=s_iow,irq,+",
                "CDEF:s_sirq=s_irq,sirq,+",
                "CDEF:s_steal=s_sirq,steal,+",
                "CDEF:s_guest=s_steal,guest,+",
                "AREA:s_guest#448844:guest",
                "GPRINT:guest:LAST:     Current\\: %4.1lf%%",
                "GPRINT:guest:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:guest:MIN:    Min\\: %4.1lf%%",
                "GPRINT:guest:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_steal#44EE44:steal",
                "GPRINT:steal:LAST:     Current\\: %4.1lf%%",
                "GPRINT:steal:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:steal:MIN:    Min\\: %4.1lf%%",
                "GPRINT:steal:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_sirq#E29136:softIRQ",
                "GPRINT:sirq:LAST:   Current\\: %4.1lf%%",
                "GPRINT:sirq:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:sirq:MIN:    Min\\: %4.1lf%%",
                "GPRINT:sirq:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_irq#888888:IRQ",
                "GPRINT:irq:LAST:       Current\\: %4.1lf%%",
                "GPRINT:irq:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:irq:MIN:    Min\\: %4.1lf%%",
                "GPRINT:irq:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_iow#EE44EE:I/O wait",
                "GPRINT:iow:LAST:  Current\\: %4.1lf%%",
                "GPRINT:iow:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:iow:MIN:    Min\\: %4.1lf%%",
                "GPRINT:iow:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_sys#44EEEE:system",
                "GPRINT:sys:LAST:    Current\\: %4.1lf%%",
                "GPRINT:sys:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:sys:MIN:    Min\\: %4.1lf%%",
                "GPRINT:sys:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:s_nice#EEEE44:nice",
                "GPRINT:nice:LAST:      Current\\: %4.1lf%%",
                "GPRINT:nice:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:nice:MIN:    Min\\: %4.1lf%%",
                "GPRINT:nice:MAX:    Max\\: %4.1lf%%\\n",
                "AREA:user#4444EE:user",
                "GPRINT:user:LAST:      Current\\: %4.1lf%%",
                "GPRINT:user:AVERAGE:    Average\\: %4.1lf%%",
                "GPRINT:user:MIN:    Min\\: %4.1lf%%",
                "GPRINT:user:MAX:    Max\\: %4.1lf%%\\n",
                "LINE1:s_guest#1F881F",
                "LINE1:s_steal#00EE00",
                "LINE1:s_sirq#D86612",
                "LINE1:s_irq#CCCCCC",
                "LINE1:s_iow#EE00EE",
                "LINE1:s_sys#00EEEE",
                "LINE1:s_nice#EEEE00",
                "LINE1:user#0000EE",
            ]
        )


def graph_context(rrdtool: str) -> None:
    """Generate context switches and forks graphs for all standard periods."""
    base_path = RRD_IMG_DIR / "kern-context.png"
    
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
                f"Context switches and forks - {period_label}",
                "--vertical-label",
                "CS & forks/s",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:cs={RRD_PATH}:kern_cs:AVERAGE",
                f"DEF:forks={RRD_PATH}:kern_forks:AVERAGE",
                "AREA:cs#44AAEE:Context switches",
                "GPRINT:cs:LAST:     Current\\: %6.0lf\\n",
                "AREA:forks#4444EE:Forks",
                "GPRINT:forks:LAST:                Current\\: %6.0lf\\n",
                "LINE1:cs#00EEEE",
                "LINE1:forks#0000EE",
            ]
        )


def graph_kernel_usage(rrdtool: str) -> None:
    """Generate dentry, file, and inode usage graphs for all standard periods."""
    base_path = RRD_IMG_DIR / "kern-usage.png"
    
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
                f"Kernel usage - {period_label}",
                "--vertical-label",
                "Percent (%)",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:dentry={RRD_PATH}:kern_dentry:AVERAGE",
                f"DEF:file={RRD_PATH}:kern_file:AVERAGE",
                f"DEF:inode={RRD_PATH}:kern_inode:AVERAGE",
                "AREA:inode#4444EE:inode",
                "GPRINT:inode:LAST:                Current\\:  %4.1lf%%\\n",
                "AREA:dentry#EEEE44:dentry",
                "GPRINT:dentry:LAST:               Current\\:  %4.1lf%%\\n",
                "AREA:file#EE44EE:file",
                "GPRINT:file:LAST:                 Current\\:  %4.1lf%%\\n",
                "LINE2:inode#0000EE",
                "LINE2:dentry#EEEE00",
                "LINE2:file#EE00EE",
            ]
        )


def generate_graphs(rrdtool: str) -> None:
    """Generate all kernel graph images."""
    graph_cpu(rrdtool)
    graph_context(rrdtool)
    graph_kernel_usage(rrdtool)
