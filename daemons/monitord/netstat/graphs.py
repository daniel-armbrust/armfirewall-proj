"""Socket state graph generation helpers."""

from __future__ import annotations

from core.process import run_command

from ..constants import RRD_IMG_DIR
from ..periods import GRAPH_PERIODS, period_image_path
from .constants import MONITORIX_GRAPH_COLORS, RRD_PATH


def graph_tcp_family(rrdtool: str, family: str, title: str, base_name: str) -> None:
    """Generate the main TCP state graph for one address family."""
    prefix = f"nstat{family}"
    base_path = RRD_IMG_DIR / base_name

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
                "Connections",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:closed={RRD_PATH}:{prefix}_closed:AVERAGE",
                f"DEF:listen={RRD_PATH}:{prefix}_listen:AVERAGE",
                f"DEF:synsent={RRD_PATH}:{prefix}_synsent:AVERAGE",
                f"DEF:synrecv={RRD_PATH}:{prefix}_synrecv:AVERAGE",
                f"DEF:estblshd={RRD_PATH}:{prefix}_estblshd:AVERAGE",
                f"DEF:finwait1={RRD_PATH}:{prefix}_finwait1:AVERAGE",
                f"DEF:finwait2={RRD_PATH}:{prefix}_finwait2:AVERAGE",
                "LINE2:closed#FFA500:CLOSED",
                "GPRINT:closed:LAST:        Current\\: %3.0lf",
                "GPRINT:closed:AVERAGE: Average\\: %3.0lf",
                "GPRINT:closed:MIN: Min\\: %3.0lf",
                "GPRINT:closed:MAX: Max\\: %3.0lf\\n",
                "LINE2:listen#44EEEE:LISTEN",
                "GPRINT:listen:LAST:        Current\\: %3.0lf",
                "GPRINT:listen:AVERAGE: Average\\: %3.0lf",
                "GPRINT:listen:MIN: Min\\: %3.0lf",
                "GPRINT:listen:MAX: Max\\: %3.0lf\\n",
                "LINE2:synsent#44EE44:SYN_SENT",
                "GPRINT:synsent:LAST:      Current\\: %3.0lf",
                "GPRINT:synsent:AVERAGE: Average\\: %3.0lf",
                "GPRINT:synsent:MIN: Min\\: %3.0lf",
                "GPRINT:synsent:MAX: Max\\: %3.0lf\\n",
                "LINE2:synrecv#4444EE:SYN_RECV",
                "GPRINT:synrecv:LAST:      Current\\: %3.0lf",
                "GPRINT:synrecv:AVERAGE: Average\\: %3.0lf",
                "GPRINT:synrecv:MIN: Min\\: %3.0lf",
                "GPRINT:synrecv:MAX: Max\\: %3.0lf\\n",
                "LINE2:estblshd#EE4444:ESTABLISHED",
                "GPRINT:estblshd:LAST:   Current\\: %3.0lf",
                "GPRINT:estblshd:AVERAGE: Average\\: %3.0lf",
                "GPRINT:estblshd:MIN: Min\\: %3.0lf",
                "GPRINT:estblshd:MAX: Max\\: %3.0lf\\n",
                "LINE2:finwait1#EE44EE:FIN_WAIT1",
                "GPRINT:finwait1:LAST:     Current\\: %3.0lf",
                "GPRINT:finwait1:AVERAGE: Average\\: %3.0lf",
                "GPRINT:finwait1:MIN: Min\\: %3.0lf",
                "GPRINT:finwait1:MAX: Max\\: %3.0lf\\n",
                "LINE2:finwait2#EEEE44:FIN_WAIT2",
                "GPRINT:finwait2:LAST:     Current\\: %3.0lf",
                "GPRINT:finwait2:AVERAGE: Average\\: %3.0lf",
                "GPRINT:finwait2:MIN: Min\\: %3.0lf",
                "GPRINT:finwait2:MAX: Max\\: %3.0lf\\n",
            ]
        )


def graph_tcp_closing_timewait(rrdtool: str) -> None:
    """Generate TCP closing and time-wait graphs for both families."""
    base_path = RRD_IMG_DIR / "netstat-tcp-closing-timewait.png"
    
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
                f"TCP CLOSING and TIME_WAIT states - {period_label}",
                "--vertical-label",
                "Connections",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:i4_closing={RRD_PATH}:nstat4_closing:AVERAGE",
                f"DEF:i6_closing={RRD_PATH}:nstat6_closing:AVERAGE",
                f"DEF:i4_timewait={RRD_PATH}:nstat4_timewait:AVERAGE",
                f"DEF:i6_timewait={RRD_PATH}:nstat6_timewait:AVERAGE",
                "LINE2:i4_closing#44EEEE:CLOSING ipv4",
                "GPRINT:i4_closing:LAST:         Current\\: %3.0lf\\n",
                "LINE2:i6_closing#4444EE:CLOSING ipv6",
                "GPRINT:i6_closing:LAST:         Current\\: %3.0lf\\n",
                "LINE2:i4_timewait#44EE44:TIME_WAIT ipv4",
                "GPRINT:i4_timewait:LAST:       Current\\: %3.0lf\\n",
                "LINE2:i6_timewait#448844:TIME_WAIT ipv6",
                "GPRINT:i6_timewait:LAST:       Current\\: %3.0lf\\n",
            ]
        )


def graph_tcp_wait_unknown(rrdtool: str) -> None:
    """Generate TCP wait and unknown state graphs for both families."""
    base_path = RRD_IMG_DIR / "netstat-tcp-wait-unknown.png"
    
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
                f"TCP wait and unknown states - {period_label}",
                "--vertical-label",
                "Connections",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:i4_closewait={RRD_PATH}:nstat4_closewait:AVERAGE",
                f"DEF:i6_closewait={RRD_PATH}:nstat6_closewait:AVERAGE",
                f"DEF:i4_lastack={RRD_PATH}:nstat4_lastack:AVERAGE",
                f"DEF:i6_lastack={RRD_PATH}:nstat6_lastack:AVERAGE",
                f"DEF:i4_unknown={RRD_PATH}:nstat4_unknown:AVERAGE",
                f"DEF:i6_unknown={RRD_PATH}:nstat6_unknown:AVERAGE",
                "LINE2:i4_closewait#44EEEE:CLOSE_WAIT ipv4",
                "GPRINT:i4_closewait:LAST:      Current\\: %3.0lf\\n",
                "LINE2:i6_closewait#4444EE:CLOSE_WAIT ipv6",
                "GPRINT:i6_closewait:LAST:      Current\\: %3.0lf\\n",
                "LINE2:i4_lastack#44EE44:LAST_ACK ipv4",
                "GPRINT:i4_lastack:LAST:        Current\\: %3.0lf\\n",
                "LINE2:i6_lastack#448844:LAST_ACK ipv6",
                "GPRINT:i6_lastack:LAST:        Current\\: %3.0lf\\n",
                "LINE2:i4_unknown#EEEE44:UNKNOWN ipv4",
                "GPRINT:i4_unknown:LAST:         Current\\: %3.0lf\\n",
                "LINE2:i6_unknown#FFA500:UNKNOWN ipv6",
                "GPRINT:i6_unknown:LAST:         Current\\: %3.0lf\\n",
            ]
        )


def graph_udp(rrdtool: str) -> None:
    """Generate UDP socket graphs for both families."""
    base_path = RRD_IMG_DIR / "netstat-udp.png"
    
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
                f"UDP sockets - {period_label}",
                "--vertical-label",
                "Listen",
                *MONITORIX_GRAPH_COLORS,
                f"DEF:i4_udp={RRD_PATH}:nstat4_udp:AVERAGE",
                f"DEF:i6_udp={RRD_PATH}:nstat6_udp:AVERAGE",
                "LINE2:i4_udp#EE44EE:UDP ipv4",
                "GPRINT:i4_udp:LAST:             Current\\: %3.0lf\\n",
                "LINE2:i6_udp#963C74:UDP ipv6",
                "GPRINT:i6_udp:LAST:             Current\\: %3.0lf\\n",
            ]
        )


def generate_graphs(rrdtool: str) -> None:
    """Generate all netstat graph images."""
    graph_tcp_family(rrdtool, "4", "IPv4 TCP socket states", "netstat-ipv4-tcp.png")
    graph_tcp_family(rrdtool, "6", "IPv6 TCP socket states", "netstat-ipv6-tcp.png")
    graph_tcp_closing_timewait(rrdtool)
    graph_tcp_wait_unknown(rrdtool)
    graph_udp(rrdtool)
