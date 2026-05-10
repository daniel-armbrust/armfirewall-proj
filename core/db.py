"""Shared SQLite helpers for ArmFirewall."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_DIR = ROOT_DIR / "db"
IFACE_DB_PATH = DB_DIR / "iface.db"
DatabaseError = sqlite3.Error
Connection = sqlite3.Connection
Cursor = sqlite3.Cursor


def connect(db_path: Path = IFACE_DB_PATH) -> Connection:
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


def ensure_exists(db_path: Path = IFACE_DB_PATH) -> None:
    """Fail early when the expected database file is missing."""
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")


@contextmanager
def connection(db_path: Path = IFACE_DB_PATH, *, require_existing: bool = True) -> Iterator[Connection]:
    """Yield a managed SQLite connection."""
    if require_existing:
        ensure_exists(db_path)

    conn = connect(db_path)
    try:
        yield conn
    finally:
        close(conn)


@contextmanager
def transaction(db_path: Path = IFACE_DB_PATH, *, require_existing: bool = True) -> Iterator[Connection]:
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


def execute(query: str, params: Sequence[Any] = (), db_path: Path = IFACE_DB_PATH) -> int:
    """Execute one SQL statement in its own transaction."""
    with transaction(db_path) as conn:
        cursor = execute_on(conn, query, params)
        return cursor.rowcount


def execute_many(query: str, params: Iterable[Sequence[Any]], db_path: Path = IFACE_DB_PATH) -> int:
    """Execute many SQL statements in one transaction."""
    with transaction(db_path) as conn:
        cursor = executemany_on(conn, query, params)
        return cursor.rowcount


def fetch_one(query: str, params: Sequence[Any] = (), db_path: Path = IFACE_DB_PATH) -> dict[str, Any] | None:
    """Fetch one row from a managed connection."""
    with connection(db_path) as conn:
        row = fetch_one_on(conn, query, params)
        return row_to_dict(row) if row is not None else None


def fetch_all(query: str, params: Sequence[Any] = (), db_path: Path = IFACE_DB_PATH) -> list[dict[str, Any]]:
    """Fetch all rows from a managed connection."""
    with connection(db_path) as conn:
        return fetch_all_on(conn, query, params)
