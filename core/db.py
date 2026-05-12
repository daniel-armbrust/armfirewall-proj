"""Shared SQLite helpers for ArmFirewall."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DatabaseError = sqlite3.Error
Connection = sqlite3.Connection
Cursor = sqlite3.Cursor


def utc_now() -> datetime:
    """Return the current UTC datetime without relying on local timezone."""
    return datetime.now(timezone.utc)


def sqlite_timestamp(value: datetime | None = None) -> str:
    """Format a datetime for storage in SQLite text columns."""
    return (value or utc_now()).strftime("%Y-%m-%d %H:%M:%S")


def parse_sqlite_timestamp(value: str | None) -> datetime | None:
    """Parse a SQLite timestamp as UTC."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def connect(db_path: Path) -> Connection:
    """Open a configured SQLite connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    configure(conn)
    
    return conn


def configure(conn: Connection) -> None:
    """Apply common SQLite pragmas to a connection."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")


def close(conn: Connection) -> None:
    """Close a SQLite connection."""
    conn.close()


def ensure_exists(db_path: Path) -> None:
    """Fail early when the expected database file is missing."""
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")


def verify_database(db_path: Path) -> None:
    """Verify that one SQLite database can be opened and queried."""
    with connection(db_path) as conn:
        fetch_one_on(conn, "SELECT 1")


def verify_databases(*db_paths: Path) -> None:
    """Verify that all provided SQLite databases can be opened and queried."""
    for db_path in db_paths:
        verify_database(db_path)


@contextmanager
def connection(db_path: Path, *, require_existing: bool = True) -> Iterator[Connection]:
    """Yield a managed SQLite connection."""
    if require_existing:
        ensure_exists(db_path)

    conn = connect(db_path)
    
    try:
        yield conn
    finally:
        close(conn)


@contextmanager
def transaction(db_path: Path, *, require_existing: bool = True) -> Iterator[Connection]:
    """Yield a connection and commit or roll back the transaction."""
    with connection(db_path, require_existing=require_existing) as conn:
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a SQLite row to a plain dictionary."""
    return dict(row)


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convert SQLite rows to plain dictionaries."""
    return [row_to_dict(row) for row in rows]


def execute_on(conn: Connection, query: str, params: Sequence[Any] = ()) -> Cursor:
    """Execute SQL using an existing connection."""
    return conn.execute(query, params)


def executemany_on(conn: Connection, query: str, params: Iterable[Sequence[Any]]) -> Cursor:
    """Execute SQL repeatedly using an existing connection."""
    return conn.executemany(query, params)


def fetch_one_on(conn: Connection, query: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    """Fetch one row using an existing connection."""
    return execute_on(conn, query, params).fetchone()


def fetch_all_on(conn: Connection, query: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    """Fetch all rows using an existing connection."""
    return rows_to_dicts(execute_on(conn, query, params).fetchall())


def execute(query: str, params: Sequence[Any] = (), *, db_path: Path) -> int:
    """Execute one SQL statement in its own transaction."""
    with transaction(db_path) as conn:
        cursor = execute_on(conn, query, params)
        return cursor.rowcount


def execute_many(query: str, params: Iterable[Sequence[Any]], *, db_path: Path) -> int:
    """Execute many SQL statements in one transaction."""
    with transaction(db_path) as conn:
        cursor = executemany_on(conn, query, params)
        return cursor.rowcount


def fetch_one(query: str, params: Sequence[Any] = (), *, db_path: Path) -> dict[str, Any] | None:
    """Fetch one row from a managed connection."""
    with connection(db_path) as conn:
        row = fetch_one_on(conn, query, params)
        return row_to_dict(row) if row is not None else None


def fetch_all(query: str, params: Sequence[Any] = (), *, db_path: Path) -> list[dict[str, Any]]:
    """Fetch all rows from a managed connection."""
    with connection(db_path) as conn:
        return fetch_all_on(conn, query, params)
