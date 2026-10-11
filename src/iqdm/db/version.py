"""Schema version of the database file compared with the version this app expects.

Kept apart from connection.py and migrations.py so that both can import it.

A file at the current version must also hold every table and column of schema.sql
(D73). Until the first real database exists, schema.sql is edited in place at
version 1 (D4), so a file made before such an edit has the right version number and
an older schema.
"""

import sqlite3
from collections.abc import Mapping
from enum import StrEnum
from functools import cache
from importlib import resources

LATEST_VERSION = 1  # bump together with a new entry in migrations.MIGRATIONS

_COLUMNS_SQL = (
    "SELECT m.name, p.name FROM sqlite_schema m JOIN pragma_table_info(m.name) p"
    " WHERE m.type = 'table' AND m.name NOT LIKE 'sqlite\\_%' ESCAPE '\\'"
)


class SchemaStatus(StrEnum):
    CURRENT = "current"
    NEEDS_UPGRADE = "needs_upgrade"  # older than the app; reads and writes refused
    TOO_NEW = "too_new"  # newer than the app; reads allowed with a warning
    NOT_IQDM = "not_iqdm"  # user_version 0 or no recordings table


def schema_sql() -> str:
    """The bundled schema.sql text."""
    return resources.files("iqdm.db").joinpath("schema.sql").read_text(encoding="utf-8")


def table_columns(conn: sqlite3.Connection) -> dict[str, frozenset[str]]:
    """The columns of each table in an open database."""
    found: dict[str, set[str]] = {}
    for table, column in conn.execute(_COLUMNS_SQL):
        found.setdefault(table, set()).add(column)
    return {table: frozenset(columns) for table, columns in found.items()}


@cache
def expected_columns() -> Mapping[str, frozenset[str]]:
    """The tables and columns of schema.sql, built once in an in-memory database."""
    conn = sqlite3.connect(":memory:", autocommit=True)
    try:
        conn.executescript(f"BEGIN;\n{schema_sql()}\nCOMMIT;")
        return table_columns(conn)
    finally:
        conn.close()


def missing_parts(conn: sqlite3.Connection) -> list[str]:
    """Tables and columns of schema.sql that the open database lacks, e.g. 'projects'."""
    have = table_columns(conn)
    missing = []
    for table, columns in sorted(expected_columns().items()):
        if table not in have:
            missing.append(table)
        else:
            missing += [f"{table}.{column}" for column in sorted(columns - have[table])]
    return missing


def schema_status(conn: sqlite3.Connection, latest: int | None = None) -> SchemaStatus:
    """Compare the file's PRAGMA user_version with `latest` (default LATEST_VERSION).

    A file at LATEST_VERSION that lacks a table or column of schema.sql is older than
    the app (D73).
    """
    expected = LATEST_VERSION if latest is None else latest
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    has_recordings = conn.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'recordings'"
    ).fetchone()
    if version == 0 or has_recordings is None:
        return SchemaStatus.NOT_IQDM
    if version < expected:
        return SchemaStatus.NEEDS_UPGRADE
    if version > expected:
        return SchemaStatus.TOO_NEW
    if expected == LATEST_VERSION and missing_parts(conn):
        return SchemaStatus.NEEDS_UPGRADE
    return SchemaStatus.CURRENT
