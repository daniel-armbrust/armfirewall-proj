"""Operating system package operations for optional services."""

from __future__ import annotations

import re
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

from core.constants import (
    ADGUARD_HOME_ARCHIVE_URL,
    ADGUARD_HOME_BINARY,
    ADGUARD_HOME_CONFIG_PATH,
    ADGUARD_HOME_DNS_HOST,
    ADGUARD_HOME_DNS_PORT,
    ADGUARD_HOME_DIR,
    ADGUARD_HOME_WORK_DIR,
)
from core.process import command_exists

from .commons import run_bounded_command


def package_manager_command(operation: str, package: str) -> list[str]:
    """Build a package manager command for install or uninstall."""
    if operation not in {"install", "uninstall"}:
        raise RuntimeError(f"Unsupported package operation: {operation}")

    if command_exists("dnf"):
        return ["dnf", "-y", "install" if operation == "install" else "remove", package]
    
    if command_exists("yum"):
        return ["yum", "-y", "install" if operation == "install" else "remove", package]
    
    if command_exists("apt-get"):
        return ["apt-get", "-y", "install" if operation == "install" else "remove", package]
    
    raise RuntimeError("No supported package manager was found.")


def package_installed(package: str) -> bool:
    """Return whether a package is currently installed."""
    if command_exists("rpm"):
        return run_bounded_command(["rpm", "-q", package], timeout=30, check=False).returncode == 0
    
    if command_exists("dpkg-query"):
        completed = run_bounded_command(["dpkg-query", "-W", "-f=${Status}", package], timeout=30, check=False)
        return completed.returncode == 0 and "install ok installed" in completed.stdout
    
    return False


def install_package(package: str) -> None:
    """Install one operating system package when missing."""
    if not package_installed(package):
        run_bounded_command(package_manager_command("install", package), timeout=600)


def uninstall_package(package: str) -> None:
    """Remove one operating system package when installed."""
    if package_installed(package):
        run_bounded_command(package_manager_command("uninstall", package), timeout=600)


def install_adguard_home() -> None:
    """Install the official ARM64 AdGuard Home runtime with executable permissions."""
    if ADGUARD_HOME_BINARY.is_file():
        ADGUARD_HOME_BINARY.chmod(0o755)
        ADGUARD_HOME_WORK_DIR.mkdir(parents=True, exist_ok=True)
        return
    if ADGUARD_HOME_BINARY.exists():
        raise RuntimeError(f"AdGuard Home binary path is not a file: {ADGUARD_HOME_BINARY}")

    ADGUARD_HOME_DIR.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adguardhome-", dir=ADGUARD_HOME_DIR.parent) as temp_dir:
        temp_path = Path(temp_dir)
        archive_path = temp_path / "adguardhome.tar.gz"
        extract_path = temp_path / "extract"
        urlretrieve(ADGUARD_HOME_ARCHIVE_URL, archive_path)

        with tarfile.open(archive_path, "r:gz") as archive:
            destination = extract_path.resolve()
            for member in archive.getmembers():
                member_path = (extract_path / member.name).resolve()
                if destination not in member_path.parents and member_path != destination:
                    raise RuntimeError("Unsafe path in AdGuard Home archive.")
            archive.extractall(extract_path, filter="data")

        source_binary = extract_path / "AdGuardHome" / "AdGuardHome"
        if not source_binary.is_file():
            raise RuntimeError("AdGuard Home archive does not contain the expected binary.")
        ADGUARD_HOME_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_binary, ADGUARD_HOME_BINARY)
        ADGUARD_HOME_BINARY.chmod(0o755)
        ADGUARD_HOME_WORK_DIR.mkdir(parents=True, exist_ok=True)


def configure_adguard_home_dns_listener() -> bool:
    """Bind AdGuard Home DNS locally on its dedicated upstream port.

    DNSMasq owns port 53 for LAN clients and forwards filtered queries to this
    listener.  Returning ``False`` is expected before AdGuard's initial setup
    has created its configuration file.
    """
    if not ADGUARD_HOME_CONFIG_PATH.is_file():
        return False

    config_text = ADGUARD_HOME_CONFIG_PATH.read_text(encoding="utf-8")
    dns_section = re.search(r"(?ms)^dns:\n(?P<body>.*?)(?=^[^\s]|\Z)", config_text)
    if dns_section is None:
        raise RuntimeError("AdGuard Home configuration does not contain a DNS section.")

    body = dns_section.group("body")
    bind_hosts = f"  bind_hosts:\n    - {ADGUARD_HOME_DNS_HOST}\n"
    if re.search(r"(?m)^  bind_hosts:\n(?:^    - .*\n)*", body):
        body = re.sub(r"(?m)^  bind_hosts:\n(?:^    - .*\n)*", bind_hosts, body, count=1)
    else:
        body = bind_hosts + body

    port_line = f"  port: {ADGUARD_HOME_DNS_PORT}"
    if re.search(r"(?m)^  port: .*?$", body):
        body = re.sub(r"(?m)^  port: .*?$", port_line, body, count=1)
    else:
        body = f"{body.rstrip()}\n{port_line}\n"

    updated_text = f"{config_text[:dns_section.start('body')]}{body}{config_text[dns_section.end('body'):]}"
    if updated_text != config_text:
        ADGUARD_HOME_CONFIG_PATH.write_text(updated_text, encoding="utf-8")
    return True


def uninstall_adguard_home() -> None:
    """Remove the locally installed AdGuard Home runtime and its data."""
    shutil.rmtree(ADGUARD_HOME_DIR, ignore_errors=True)
    shutil.rmtree(ADGUARD_HOME_WORK_DIR, ignore_errors=True)
