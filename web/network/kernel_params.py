from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web.constants import TEMPLATE_DIR


templates = Jinja2Templates(directory=TEMPLATE_DIR)


@dataclass(frozen=True)
class KernelParam:
    """Describe one global Linux kernel parameter exposed by /proc/sys."""

    name: str
    proc_path: str
    category: str
    default_value: str
    description: str


GLOBAL_KERNEL_PARAMS = [
    KernelParam(
        name="net.ipv4.ip_forward",
        proc_path="/proc/sys/net/ipv4/ip_forward",
        category="IPv4",
        default_value="0",
        description="Enables IPv4 packet forwarding between interfaces.",
    ),
    KernelParam(
        name="net.ipv4.conf.all.rp_filter",
        proc_path="/proc/sys/net/ipv4/conf/all/rp_filter",
        category="IPv4",
        default_value="0",
        description="Controls global reverse path filtering for IPv4 source validation.",
    ),
    KernelParam(
        name="net.ipv4.conf.default.rp_filter",
        proc_path="/proc/sys/net/ipv4/conf/default/rp_filter",
        category="IPv4",
        default_value="0",
        description="Controls reverse path filtering inherited by new IPv4 interfaces.",
    ),
    KernelParam(
        name="net.ipv4.conf.all.accept_redirects",
        proc_path="/proc/sys/net/ipv4/conf/all/accept_redirects",
        category="IPv4",
        default_value="1",
        description="Controls whether IPv4 ICMP redirect messages are accepted globally.",
    ),
    KernelParam(
        name="net.ipv4.conf.default.accept_redirects",
        proc_path="/proc/sys/net/ipv4/conf/default/accept_redirects",
        category="IPv4",
        default_value="1",
        description="Controls whether new IPv4 interfaces accept ICMP redirect messages.",
    ),
    KernelParam(
        name="net.ipv4.conf.all.send_redirects",
        proc_path="/proc/sys/net/ipv4/conf/all/send_redirects",
        category="IPv4",
        default_value="1",
        description="Controls whether IPv4 ICMP redirect messages are sent globally.",
    ),
    KernelParam(
        name="net.ipv4.conf.default.send_redirects",
        proc_path="/proc/sys/net/ipv4/conf/default/send_redirects",
        category="IPv4",
        default_value="1",
        description="Controls whether new IPv4 interfaces send ICMP redirect messages.",
    ),
    KernelParam(
        name="net.ipv4.conf.all.secure_redirects",
        proc_path="/proc/sys/net/ipv4/conf/all/secure_redirects",
        category="IPv4",
        default_value="1",
        description="Controls whether secure IPv4 redirects from known gateways are accepted globally.",
    ),
    KernelParam(
        name="net.ipv4.conf.default.secure_redirects",
        proc_path="/proc/sys/net/ipv4/conf/default/secure_redirects",
        category="IPv4",
        default_value="1",
        description="Controls whether new IPv4 interfaces accept secure redirects from known gateways.",
    ),
    KernelParam(
        name="net.ipv4.tcp_syncookies",
        proc_path="/proc/sys/net/ipv4/tcp_syncookies",
        category="TCP",
        default_value="1",
        description="Enables SYN cookies to help protect against SYN flood attacks.",
    ),
    KernelParam(
        name="net.ipv4.tcp_timestamps",
        proc_path="/proc/sys/net/ipv4/tcp_timestamps",
        category="TCP",
        default_value="1",
        description="Enables TCP timestamps used by PAWS and round-trip time measurement.",
    ),
    KernelParam(
        name="net.ipv4.tcp_sack",
        proc_path="/proc/sys/net/ipv4/tcp_sack",
        category="TCP",
        default_value="1",
        description="Enables TCP selective acknowledgements.",
    ),
    KernelParam(
        name="net.ipv4.tcp_window_scaling",
        proc_path="/proc/sys/net/ipv4/tcp_window_scaling",
        category="TCP",
        default_value="1",
        description="Enables TCP window scaling for high bandwidth-delay paths.",
    ),
    KernelParam(
        name="net.ipv4.tcp_fin_timeout",
        proc_path="/proc/sys/net/ipv4/tcp_fin_timeout",
        category="TCP",
        default_value="60",
        description="Defines how long sockets stay in FIN-WAIT-2 before timeout.",
    ),
    KernelParam(
        name="net.ipv4.tcp_keepalive_time",
        proc_path="/proc/sys/net/ipv4/tcp_keepalive_time",
        category="TCP",
        default_value="7200",
        description="Defines idle time before TCP starts sending keepalive probes.",
    ),
    KernelParam(
        name="net.ipv4.tcp_keepalive_intvl",
        proc_path="/proc/sys/net/ipv4/tcp_keepalive_intvl",
        category="TCP",
        default_value="75",
        description="Defines the interval between TCP keepalive probes.",
    ),
    KernelParam(
        name="net.ipv4.tcp_keepalive_probes",
        proc_path="/proc/sys/net/ipv4/tcp_keepalive_probes",
        category="TCP",
        default_value="9",
        description="Defines how many TCP keepalive probes are sent before dropping a connection.",
    ),
    KernelParam(
        name="net.ipv4.tcp_max_syn_backlog",
        proc_path="/proc/sys/net/ipv4/tcp_max_syn_backlog",
        category="TCP",
        default_value="system-dependent",
        description="Defines the maximum queued half-open TCP connection requests.",
    ),
    KernelParam(
        name="net.ipv4.tcp_syn_retries",
        proc_path="/proc/sys/net/ipv4/tcp_syn_retries",
        category="TCP",
        default_value="6",
        description="Defines how many SYN retransmits are attempted for outbound TCP connections.",
    ),
    KernelParam(
        name="net.ipv4.tcp_synack_retries",
        proc_path="/proc/sys/net/ipv4/tcp_synack_retries",
        category="TCP",
        default_value="5",
        description="Defines how many SYN-ACK retransmits are attempted for passive TCP opens.",
    ),
    KernelParam(
        name="net.ipv4.tcp_retries2",
        proc_path="/proc/sys/net/ipv4/tcp_retries2",
        category="TCP",
        default_value="15",
        description="Defines how many retransmits are attempted before killing an established TCP connection.",
    ),
    KernelParam(
        name="net.ipv4.icmp_echo_ignore_all",
        proc_path="/proc/sys/net/ipv4/icmp_echo_ignore_all",
        category="ICMP",
        default_value="0",
        description="Controls whether the host ignores all ICMP echo requests.",
    ),
    KernelParam(
        name="net.ipv4.icmp_echo_ignore_broadcasts",
        proc_path="/proc/sys/net/ipv4/icmp_echo_ignore_broadcasts",
        category="ICMP",
        default_value="1",
        description="Controls whether ICMP echo requests sent to broadcast addresses are ignored.",
    ),
    KernelParam(
        name="net.ipv4.icmp_ignore_bogus_error_responses",
        proc_path="/proc/sys/net/ipv4/icmp_ignore_bogus_error_responses",
        category="ICMP",
        default_value="1",
        description="Controls whether bogus ICMP error responses are ignored.",
    ),
    KernelParam(
        name="net.ipv4.icmp_ratelimit",
        proc_path="/proc/sys/net/ipv4/icmp_ratelimit",
        category="ICMP",
        default_value="1000",
        description="Defines the minimum spacing in milliseconds between certain ICMP replies.",
    ),
    KernelParam(
        name="net.ipv4.icmp_ratemask",
        proc_path="/proc/sys/net/ipv4/icmp_ratemask",
        category="ICMP",
        default_value="6168",
        description="Defines which ICMP message types are subject to rate limiting.",
    ),
    KernelParam(
        name="net.ipv4.neigh.default.gc_thresh1",
        proc_path="/proc/sys/net/ipv4/neigh/default/gc_thresh1",
        category="Neighbor",
        default_value="128",
        description="Defines the first garbage collection threshold for IPv4 neighbor entries.",
    ),
    KernelParam(
        name="net.ipv4.neigh.default.gc_thresh2",
        proc_path="/proc/sys/net/ipv4/neigh/default/gc_thresh2",
        category="Neighbor",
        default_value="512",
        description="Defines the second garbage collection threshold for IPv4 neighbor entries.",
    ),
    KernelParam(
        name="net.ipv4.neigh.default.gc_thresh3",
        proc_path="/proc/sys/net/ipv4/neigh/default/gc_thresh3",
        category="Neighbor",
        default_value="1024",
        description="Defines the hard garbage collection threshold for IPv4 neighbor entries.",
    ),
    KernelParam(
        name="net.ipv4.neigh.default.base_reachable_time_ms",
        proc_path="/proc/sys/net/ipv4/neigh/default/base_reachable_time_ms",
        category="Neighbor",
        default_value="30000",
        description="Defines the base reachable time in milliseconds for IPv4 neighbor entries.",
    ),
    KernelParam(
        name="net.ipv4.neigh.default.retrans_time_ms",
        proc_path="/proc/sys/net/ipv4/neigh/default/retrans_time_ms",
        category="Neighbor",
        default_value="1000",
        description="Defines retransmission time in milliseconds for IPv4 neighbor discovery.",
    ),
    KernelParam(
        name="net.ipv6.conf.all.forwarding",
        proc_path="/proc/sys/net/ipv6/conf/all/forwarding",
        category="IPv6",
        default_value="0",
        description="Enables IPv6 packet forwarding globally.",
    ),
    KernelParam(
        name="net.ipv6.conf.default.forwarding",
        proc_path="/proc/sys/net/ipv6/conf/default/forwarding",
        category="IPv6",
        default_value="0",
        description="Controls IPv6 forwarding inherited by new interfaces.",
    ),
    KernelParam(
        name="net.ipv6.conf.all.accept_redirects",
        proc_path="/proc/sys/net/ipv6/conf/all/accept_redirects",
        category="IPv6",
        default_value="1",
        description="Controls whether IPv6 redirect messages are accepted globally.",
    ),
    KernelParam(
        name="net.ipv6.conf.default.accept_redirects",
        proc_path="/proc/sys/net/ipv6/conf/default/accept_redirects",
        category="IPv6",
        default_value="1",
        description="Controls whether new IPv6 interfaces accept redirect messages.",
    ),
    KernelParam(
        name="net.ipv6.conf.all.accept_ra",
        proc_path="/proc/sys/net/ipv6/conf/all/accept_ra",
        category="IPv6",
        default_value="1",
        description="Controls whether IPv6 router advertisements are accepted globally.",
    ),
    KernelParam(
        name="net.ipv6.conf.default.accept_ra",
        proc_path="/proc/sys/net/ipv6/conf/default/accept_ra",
        category="IPv6",
        default_value="1",
        description="Controls whether new IPv6 interfaces accept router advertisements.",
    ),
    KernelParam(
        name="net.ipv6.conf.all.disable_ipv6",
        proc_path="/proc/sys/net/ipv6/conf/all/disable_ipv6",
        category="IPv6",
        default_value="0",
        description="Controls whether IPv6 is disabled globally.",
    ),
    KernelParam(
        name="net.ipv6.conf.default.disable_ipv6",
        proc_path="/proc/sys/net/ipv6/conf/default/disable_ipv6",
        category="IPv6",
        default_value="0",
        description="Controls whether IPv6 is disabled by default on new interfaces.",
    ),
    KernelParam(
        name="net.netfilter.nf_conntrack_max",
        proc_path="/proc/sys/net/netfilter/nf_conntrack_max",
        category="Conntrack",
        default_value="system-dependent",
        description="Defines the maximum number of tracked connections.",
    ),
    KernelParam(
        name="net.netfilter.nf_conntrack_tcp_timeout_established",
        proc_path="/proc/sys/net/netfilter/nf_conntrack_tcp_timeout_established",
        category="Conntrack",
        default_value="432000",
        description="Defines established TCP connection tracking timeout in seconds.",
    ),
    KernelParam(
        name="net.netfilter.nf_conntrack_tcp_timeout_time_wait",
        proc_path="/proc/sys/net/netfilter/nf_conntrack_tcp_timeout_time_wait",
        category="Conntrack",
        default_value="120",
        description="Defines TCP TIME-WAIT connection tracking timeout in seconds.",
    ),
    KernelParam(
        name="net.netfilter.nf_conntrack_udp_timeout",
        proc_path="/proc/sys/net/netfilter/nf_conntrack_udp_timeout",
        category="Conntrack",
        default_value="30",
        description="Defines UDP connection tracking timeout in seconds.",
    ),
    KernelParam(
        name="net.netfilter.nf_conntrack_udp_timeout_stream",
        proc_path="/proc/sys/net/netfilter/nf_conntrack_udp_timeout_stream",
        category="Conntrack",
        default_value="120",
        description="Defines UDP stream connection tracking timeout in seconds.",
    ),
]


def page_context(request: Request, title: str) -> dict[str, Any]:
    """Create shared template context for kernel parameter pages."""
    return {
        "request": request,
        "title": title,
        "user_name": "admin",
        "current_path": request.url.path,
    }


def render_kernel_params(request: Request) -> HTMLResponse:
    """Render the Network / Kernel Params page."""
    return templates.TemplateResponse(
        request,
        "network/kernel_params.html",
        context=page_context(request, "Kernel Params"),
    )


def read_kernel_param(path: str) -> tuple[str, bool, str]:
    """Read one global kernel parameter and report availability."""
    proc_path = Path(path)
    if not proc_path.exists():
        return "-", False, "missing"
    try:
        value = proc_path.read_text(encoding="utf-8").strip()
    except PermissionError:
        return "-", False, "permission denied"
    except OSError as exc:
        return "-", False, str(exc)
    return value, True, "ok"


def kernel_param_row(param: KernelParam) -> dict[str, Any]:
    """Build one serializable kernel parameter row."""
    current_value, available, read_status = read_kernel_param(param.proc_path)
    return {
        "name": param.name,
        "proc_path": param.proc_path,
        "category": param.category,
        "description": param.description,
        "default_value": param.default_value,
        "current_value": current_value,
        "available": 1 if available else 0,
        "read_status": read_status,
    }


def param_by_path(proc_path: str) -> KernelParam:
    """Return the allowed kernel parameter for a /proc/sys path."""
    for param in GLOBAL_KERNEL_PARAMS:
        if param.proc_path == proc_path:
            return param
    raise HTTPException(status_code=400, detail="Unsupported kernel parameter path.")


def get_kernel_params() -> dict[str, Any]:
    """Return global kernel parameters with summary metadata."""
    rows = [kernel_param_row(param) for param in GLOBAL_KERNEL_PARAMS]
    available = sum(1 for row in rows if row["available"] == 1)
    enabled = sum(1 for row in rows if row["current_value"] == "1")
    return {
        "summary": {
            "items": len(rows),
            "available": available,
            "enabled": enabled,
            "missing": len(rows) - available,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "params": rows,
    }


def update_kernel_param_current_value(payload: dict[str, Any]) -> dict[str, Any]:
    """Write one allowed global kernel parameter runtime value."""
    proc_path = str(payload.get("proc_path", "")).strip()
    current_value = str(payload.get("current_value", "")).strip()

    if not proc_path:
        raise HTTPException(status_code=400, detail="proc_path is required.")
    if current_value == "":
        raise HTTPException(status_code=400, detail="current_value is required.")

    param = param_by_path(proc_path)
    path = Path(param.proc_path)
    try:
        path.write_text(f"{current_value}\n", encoding="utf-8")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied writing kernel parameter.") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"param": kernel_param_row(param)}
