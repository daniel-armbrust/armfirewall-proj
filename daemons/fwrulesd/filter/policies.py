"""Filter chain policy database helpers."""

from __future__ import annotations

from core import db


def require_filter_chain_policies(conn: db.Connection) -> None:
    """Fail clearly when the filter chain policy table was not created."""
    row = db.fetch_one_on(
        conn,
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'filter_chain_policies'",
    )

    if row is None:
        raise RuntimeError("Missing filter_chain_policies table. Run install.sh to create the firewall schema.")
