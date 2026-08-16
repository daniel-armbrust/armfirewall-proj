"""Structured data parsed from BIRD diagnostics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BirdProtocolRow:
    """One parsed row from birdcl show protocols."""

    name: str
    proto: str
    table_name: str | None
    state: str
    since: str | None
    info: str | None
    raw_line: str


@dataclass(frozen=True)
class BirdRouteRow:
    """One parsed row from birdcl show route output."""

    table_name: str | None
    route_prefix: str
    route_type: str | None
    source_protocol: str | None
    since: str | None
    selected: bool
    metric: int | None
    next_hop: str | None
    iface_name: str | None
    raw_route: str
    raw_detail: str | None
