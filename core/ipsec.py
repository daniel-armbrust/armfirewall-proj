"""Shared helpers for reading Libreswan IPsec runtime state."""

from __future__ import annotations

import re

from core.process import command_exists, run_command


IPSEC_COMMAND = "ipsec"
IPSEC_STATUS_TIMEOUT_SECONDS = 5


def ipsec_output(*args: str) -> str:
    """Return output from one ipsec status command."""
    if not command_exists(IPSEC_COMMAND):
        return ""

    completed = run_command(
        [IPSEC_COMMAND, *args],
        check=False,
        timeout=IPSEC_STATUS_TIMEOUT_SECONDS,
    )
    return "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()


def connection_names_from_trafficstatus(output: str) -> set[str]:
    """Return connection names that have active IPsec traffic status."""
    names: set[str] = set()

    for line in output.splitlines():
        match = re.search(r'"([^"]+)"', line)
        if match:
            names.add(match.group(1))

    return names


def connection_names_from_status(output: str) -> set[str]:
    """Return connection names that have an established child SA."""
    names: set[str] = set()
    established_tokens = ("ESTABLISHED_CHILD_SA", "IPsec SA established")

    for line in output.splitlines():
        if not any(token in line for token in established_tokens):
            continue

        match = re.search(r'"([^"]+)"', line)
        if match:
            names.add(match.group(1))

    return names


def established_connection_names() -> set[str]:
    """Return Libreswan connection names with established IPsec SAs."""
    names = connection_names_from_trafficstatus(ipsec_output("trafficstatus"))

    if names:
        return names

    return connection_names_from_status(ipsec_output("status"))
