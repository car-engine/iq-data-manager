"""Schema version of the database file compared with the version this app expects.

Kept apart from connection.py and migrations.py so that both can import it.
"""

import sqlite3
from enum import StrEnum

LATEST_VERSION = 1  # bump together with a new entry in migrations.MIGRATIONS


class SchemaStatus(StrEnum):
    CURRENT = "current"
    NEEDS_UPGRADE = "needs_upgrade"  # older than the app; reads and writes refused
    TOO_NEW = "too_new"  # newer than the app; reads allowed with a warning
    NOT_IQDM = "not_iqdm"  # user_version 0 or no recordings table


def schema_status(conn: sqlite3.Connection, latest: int | None = None) -> SchemaStatus:
    """Compare the file's PRAGMA user_version with `latest` (default LATEST_VERSION)."""
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
    return SchemaStatus.CURRENT
