"""Operating system package operations for optional services."""

from __future__ import annotations

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
