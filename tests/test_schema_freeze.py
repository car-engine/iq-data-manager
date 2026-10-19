"""The frozen version 1 schema (DECISIONS.md D77, O20).

`tests/schemas/v1.sql` holds `schema.sql` as released in `v1.0.0`. The real catalogue
was made from it. A database built from it and upgraded must have the structure of a
database built from the current `schema.sql`. All files live in tmp_path.
"""

import hashlib
import sqlite3
from pathlib import Path

import pytest

from iqdm.db import version
from iqdm.db.connection import create_database
from iqdm.db.migrations import upgrade

V1_SQL = Path(__file__).parent / "schemas" / "v1.sql"
# SHA-256 of v1.sql with LF line endings: the bytes of schema.sql at the tag v1.0.0.
V1_SHA256 = "0416405082f3760c120afdf6c4682fa5844ddaa957f6e273942ebea431d63ff2"


def build_v1(path: Path) -> None:
    conn = sqlite3.connect(path, autocommit=True)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(f"BEGIN IMMEDIATE;\n{V1_SQL.read_text(encoding='utf-8')}\nCOMMIT;")
    finally:
        conn.close()


def structure(path: Path) -> dict[str, object]:
    """Tables with their columns, indexes with their columns, and trigger names."""
    conn = sqlite3.connect(path)
    try:
        objects = conn.execute(
            "SELECT type, name, tbl_name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        tables = {
            name: {
                row[1]: row[2:]  # type, notnull, default, pk
                for row in conn.execute(f"PRAGMA table_info({name})")
            }
            for kind, name, _ in objects
            if kind == "table"
        }
        indexes = {
            name: (table, tuple(row[2] for row in conn.execute(f"PRAGMA index_info({name})")))
            for kind, name, table in objects
            if kind == "index"
        }
        triggers = {(name, table) for kind, name, table in objects if kind == "trigger"}
        return {"tables": tables, "indexes": indexes, "triggers": triggers}
    finally:
        conn.close()


def statements(path: Path) -> set[tuple[str, str, str]]:
    conn = sqlite3.connect(path)
    try:
        return set(conn.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL"))
    finally:
        conn.close()


def user_version(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def test_the_frozen_schema_is_the_released_one():
    text = V1_SQL.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == V1_SHA256


def test_a_version_1_database_upgraded_has_the_current_structure(tmp_path):
    old = tmp_path / "v1.db"
    build_v1(old)
    assert user_version(old) == 1
    result = upgrade(old)
    assert result.to_version == version.LATEST_VERSION
    assert user_version(old) == version.LATEST_VERSION

    new = tmp_path / "current.db"
    create_database(new)
    assert structure(old) == structure(new)


@pytest.mark.skipif(version.LATEST_VERSION != 1, reason="a migration exists")
def test_schema_sql_is_not_edited_in_place_while_the_version_is_1(tmp_path):
    """Until the first migration, schema.sql must build exactly the version 1 schema.

    Comments outside the statements may change. Any change to a table, index or
    trigger needs a numbered migration and a higher LATEST_VERSION (HANDOFF.md,
    section 5).
    """
    old = tmp_path / "v1.db"
    build_v1(old)
    new = tmp_path / "current.db"
    create_database(new)
    assert statements(old) == statements(new)
