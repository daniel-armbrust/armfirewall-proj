"""Supervise odhcp6c for legacy NetworkManager IPv6 prefix delegation."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from core import log as logger

LOG_SOURCE = "nmlegacyipv6pd.py"
ROOT_DIR = Path(__file__).resolve().parents[2]
STOP_REQUESTED = False


def setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required IPv6 PD setting: {name}")
    return value


def command() -> list[str]:
    wan = setting("ARMFW_IPV6PD_WAN")
    prefix_length = setting("ARMFW_IPV6PD_PREFIX_LENGTH")
    odhcp6c = os.environ.get("ARMFW_ODHCP6C_BIN", "odhcp6c")
    hook = ROOT_DIR / "daemons" / "nmlegacyipv6pd" / "odhcp6c_hook.py"
    return [odhcp6c, "-s", str(hook), "-N", "try", "-P", prefix_length, "-F", wan]


def request_stop(_signal: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def main() -> None:
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    logger.info("Starting NetworkManager legacy IPv6 prefix-delegation client.", source=LOG_SOURCE)
    while not STOP_REQUESTED:
        child = subprocess.Popen(command())
        while child.poll() is None and not STOP_REQUESTED:
            time.sleep(1)
        if STOP_REQUESTED and child.poll() is None:
            child.terminate()
        status = child.wait()
        if not STOP_REQUESTED:
            logger.warning(f"odhcp6c exited with status {status}; retrying in 5 seconds.", source=LOG_SOURCE)
            time.sleep(5)
    logger.info("Stopping NetworkManager legacy IPv6 prefix-delegation client.", source=LOG_SOURCE)
