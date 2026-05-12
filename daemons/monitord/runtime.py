"""Runtime helpers for the ArmFirewall monitoring daemon."""

from __future__ import annotations

import shutil

from .constants import RRD_DIR, RRD_IMG_DIR


def require_rrdtool() -> str:
    """Return the rrdtool binary path or fail clearly."""
    rrdtool = shutil.which("rrdtool")
    if not rrdtool:
        raise RuntimeError("rrdtool command was not found.")
    return rrdtool


def ensure_directories() -> None:
    """Create the RRD data and image directories."""
    RRD_DIR.mkdir(parents=True, exist_ok=True)
    RRD_IMG_DIR.mkdir(parents=True, exist_ok=True)
