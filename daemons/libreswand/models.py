"""Data models used by the Libreswan work request executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LibreswanWorkRequest:
    """Hold one decoded Libreswan work request context."""

    work_request_id: str
    request_uid: str
    category_name: str
    category: str
    family: str
    target_name: str
    action_name: str
    target_rule_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class LibreswanConnection:
    """One persisted Libreswan tunnel definition."""

    id: int
    conn_name: str
    enabled: int
    left_addr: str
    left_id: str
    right_addr: str
    authby: str
    shared_secret: str
    leftsubnet: str
    rightsubnet: str
    auto: str
    mark: str
    vti_interface: str
    vti_addr: str
    vti_routing: str
    ikev2: str
    ike: str
    phase2alg: str
    encapsulation: str
    ikelifetime: str
    salifetime: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "LibreswanConnection":
        """Build a connection model from a SQLite row dictionary."""
        return cls(
            id=int(row["id"]),
            conn_name=str(row["conn_name"]),
            enabled=int(row["enabled"]),
            left_addr=str(row["left_addr"]),
            left_id=str(row["left_id"] or ""),
            right_addr=str(row["right_addr"]),
            authby=str(row["authby"] or "secret"),
            shared_secret=str(row["shared_secret"] or ""),
            leftsubnet=str(row["leftsubnet"] or "0.0.0.0/0"),
            rightsubnet=str(row["rightsubnet"] or "0.0.0.0/0"),
            auto=str(row["auto"] or "start"),
            mark=str(row["mark"]),
            vti_interface=str(row["vti_interface"]),
            vti_addr=str(row.get("vti_addr") or ""),
            vti_routing=str(row["vti_routing"] or "no"),
            ikev2=str(row["ikev2"] or "no"),
            ike=str(row["ike"]),
            phase2alg=str(row["phase2alg"]),
            encapsulation=str(row["encapsulation"] or "yes"),
            ikelifetime=str(row["ikelifetime"] or "28800s"),
            salifetime=str(row["salifetime"] or "3600s"),
        )
