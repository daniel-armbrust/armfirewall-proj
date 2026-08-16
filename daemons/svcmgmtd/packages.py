"""Operating system package operations for optional services."""

from __future__ import annotations

import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

from core.constants import (
    ADGUARD_HOME_ARCHIVE_URL,
    ADGUARD_HOME_BINARY,
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
    """Download the official ARM64 AdGuard Home release when it is missing."""
    if ADGUARD_HOME_BINARY.exists():
        return

    ADGUARD_HOME_DIR.parent.mkdir(parents=True, exist_ok=True)
    ADGUARD_HOME_WORK_DIR.mkdir(parents=True, exist_ok=True)
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

        source_dir = extract_path / "AdGuardHome"
        source_binary = source_dir / "AdGuardHome"
        if not source_binary.is_file():
            raise RuntimeError("AdGuard Home archive does not contain the expected binary.")
        source_binary.chmod(0o755)
        shutil.move(str(source_dir), str(ADGUARD_HOME_DIR))


def uninstall_adguard_home() -> None:
    """Remove the locally installed AdGuard Home runtime and its data."""
    shutil.rmtree(ADGUARD_HOME_DIR, ignore_errors=True)
    shutil.rmtree(ADGUARD_HOME_WORK_DIR, ignore_errors=True)
