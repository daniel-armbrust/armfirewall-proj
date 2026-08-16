"""Parsers for BIRD diagnostic command output."""

from __future__ import annotations

import re

from .models import BirdProtocolRow, BirdRouteRow


ROUTE_LINE_RE = re.compile(
    r"^(?P<prefix>\S+)\s+(?P<rtype>\S+)\s+\[(?P<source>\S+)\s+(?P<since>[^\]]+)\]\s+"
    r"(?P<selected>\*)?\s*(?:\((?P<metric>\d+)\))?"
)


def parse_show_protocols(output: str) -> list[BirdProtocolRow]:
    """Parse birdcl show protocols tabular output."""
    rows: list[BirdProtocolRow] = []
    header_seen = False

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("BIRD "):
            continue
        if stripped.startswith("Name") and "Proto" in stripped and "State" in stripped:
            header_seen = True
            continue
        if not header_seen:
            continue

        parts = stripped.split(None, 5)
        if len(parts) < 5:
            continue

        name, proto, table_name, state, since = parts[:5]
        info = parts[5].strip() if len(parts) > 5 and parts[5].strip() else None
        rows.append(BirdProtocolRow(name, proto, None if table_name == "---" else table_name, state, since, info, line))

    return rows


def parse_show_routes(output: str) -> list[BirdRouteRow]:
    """Parse birdcl show route output into structured route rows."""
    rows: list[BirdRouteRow] = []
    pending: BirdRouteRow | None = None
    current_table: str | None = None

    def flush_pending() -> None:
        nonlocal pending
        if pending is not None:
            rows.append(pending)
            pending = None

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("BIRD "):
            continue
        if stripped.startswith("Table "):
            flush_pending()
            current_table = stripped.removeprefix("Table ").rstrip(":") or None
            continue

        match = ROUTE_LINE_RE.match(stripped)
        if match:
            flush_pending()
            metric_text = match.group("metric")
            pending = BirdRouteRow(
                current_table, match.group("prefix"), match.group("rtype"), match.group("source"),
                match.group("since"), bool(match.group("selected")),
                int(metric_text) if metric_text is not None else None, None, None, line, None,
            )
            continue

        if pending is None:
            continue

        next_hop = pending.next_hop
        iface_name = pending.iface_name
        via_match = re.search(r"\bvia\s+(\S+)\s+on\s+(\S+)", stripped)
        dev_match = re.search(r"\bdev\s+(\S+)", stripped)
        if via_match:
            next_hop, iface_name = via_match.groups()
        elif dev_match:
            iface_name = dev_match.group(1)

        pending = BirdRouteRow(
            pending.table_name, pending.route_prefix, pending.route_type, pending.source_protocol,
            pending.since, pending.selected, pending.metric, next_hop, iface_name,
            pending.raw_route, stripped,
        )

    flush_pending()
    return rows
