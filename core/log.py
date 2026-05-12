"""Shared daemon logging helpers for ArmFirewall."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from core import db
from core.constants import LOG_DB_PATH


ERROR_LEVELS = {"ERROR", "FATAL"}


def default_source() -> str:
    """Return the current process name used as the log source."""
    return Path(sys.argv[0]).name or "armfirewall"


def format_message(level: str, message: str, source: str) -> str:
    """Build the line written to the console streams."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[{timestamp}] [{source}] [{level}] {message}"


def write_console(level: str, message: str, source: str) -> None:
    """Write one log line to stdout or stderr based on severity."""
    stream = sys.stderr if level in ERROR_LEVELS else sys.stdout
    print(format_message(level, message, source), file=stream, flush=True)


def write_database(level: str, message: str, source: str) -> None:
    """Store one log line in logs.db when the database is accessible."""
    try:
        with db.connection(LOG_DB_PATH) as conn:
            db.execute_on(
                conn,
                """
                INSERT INTO logs (source, level, message)
                VALUES (?, ?, ?)
                """,
                (source, level, message),
            )
            conn.commit()
    except Exception:  # noqa: BLE001 - logging must never break daemon execution.
        return


def write(level: str, message: str, source: str | None = None) -> None:
    """Write one daemon log message to console and logs.db when possible."""
    resolved_source = source or default_source()
    resolved_level = level.upper()
    write_console(resolved_level, message, resolved_source)
    write_database(resolved_level, message, resolved_source)


def log(message: str, source: str | None = None) -> None:
    """Write an informational daemon log message."""
    write("INFO", message, source)


def info(message: str, source: str | None = None) -> None:
    """Write an informational daemon log message."""
    write("INFO", message, source)


def warning(message: str, source: str | None = None) -> None:
    """Write a warning daemon log message."""
    write("WARNING", message, source)


def error(message: str, source: str | None = None) -> None:
    """Write an error daemon log message."""
    write("ERROR", message, source)


def fatal(message: str, source: str | None = None) -> None:
    """Write a fatal daemon log message."""
    write("FATAL", message, source)
