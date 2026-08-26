"""System resolver configuration managed by DNSMasq."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

RESOLV_CONF_PATH = Path("/etc/resolv.conf")
LOOPBACK_NAMESERVER = "127.0.0.1"
DEFAULT_NAMESERVERS = ("1.1.1.1", "8.8.8.8")


def _chattr(immutable: bool) -> None:
    """Set or clear the immutable attribute of resolv.conf."""
    command = shutil.which("chattr")
    if not command:
        raise RuntimeError("chattr is required to protect /etc/resolv.conf.")

    operation = "+i" if immutable else "-i"
    result = subprocess.run(
        [command, operation, str(RESOLV_CONF_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Could not run chattr {operation} on /etc/resolv.conf: {detail}")


def configure_system_resolver(dns_enabled: bool) -> None:
    """Set the system resolver and protect it while DNSMasq is enabled."""
    nameservers = (LOOPBACK_NAMESERVER,) if dns_enabled else DEFAULT_NAMESERVERS
    content = "".join(f"nameserver {server}\n" for server in nameservers)

    _chattr(immutable=False)
    RESOLV_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = RESOLV_CONF_PATH.with_name(".resolv.conf.armfirewall.tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(RESOLV_CONF_PATH)

    if dns_enabled:
        _chattr(immutable=True)

