"""Tests for iqdm.db.migrations with synthetic migrations. All files live in tmp_path."""

import sqlite3
from datetime import UTC, datetime

import pytest

from iqdm.db import migrations, version
from iqdm.db.connection import SchemaVersionError, connect, open_db
from iqdm.db.migrations import Migration, MigrationError, backup_database, upgrade

NOW = datetime(2026, 10, 2, 3, 4, 5, tzinfo=UTC)


def user_version(path) -> int:
    raw = sqlite3.connect(path)
    try:
        return raw.execute("PRAGMA user_version").fetchone()[0]
    finally:
        raw.close()


def columns(path, table) -> set[str]:
    raw = sqlite3.connect(path)
    try:
        return {r[1] for r in raw.execute(f"PRAGMA table_info({table})")}
    finally:
        raw.close()


def add_column(name: str):
    def apply(conn: sqlite3.Connection) -> None:
        conn.execute(f"ALTER TABLE recordings ADD COLUMN {name} TEXT")

    return apply


def fail_after(name: str):
    def apply(conn: sqlite3.Connection) -> None:
        conn.execute(f"ALTER TABLE recordings ADD COLUMN {name} TEXT")
        raise RuntimeError("step failed")

    return apply


M1 = Migration(1, "add extra_a", add_column("extra_a"))
M2 = Migration(2, "add extra_b", add_column("extra_b"))


def files_in(folder) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_matches_latest_version():
    assert len(migrations.MIGRATIONS) == version.LATEST_VERSION - 1
    froms = [m.from_version for m in migrations.MIGRATIONS]
    assert froms == list(range(1, version.LATEST_VERSION))


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def test_current_database_needs_nothing(db_path):
    before = files_in(db_path.parent)
    result = upgrade(db_path, now=NOW)
    assert result.from_version == result.to_version == 1
    assert result.backup_path is None
    assert result.applied == ()
    assert files_in(db_path.parent) == before


def test_one_step(db_path):
    result = upgrade(db_path, migrations=[M1], latest=2, now=NOW)
    assert (result.from_version, result.to_version) == (1, 2)
    assert result.applied == ("add extra_a",)
    assert result.backup_path == db_path.with_name("catalog.v1-backup-20261002T030405Z.db")
    assert user_version(db_path) == 2
    assert "extra_a" in columns(db_path, "recordings")
    # The backup holds the old schema.
    assert user_version(result.backup_path) == 1
    assert "extra_a" not in columns(result.backup_path, "recordings")


def test_two_steps(db_path):
    result = upgrade(db_path, migrations=[M2, M1], latest=3, now=NOW)
    assert result.applied == ("add extra_a", "add extra_b")
    assert user_version(db_path) == 3
    assert {"extra_a", "extra_b"} <= columns(db_path, "recordings")


def test_backup_keeps_data(db_path):
    raw = sqlite3.connect(db_path, autocommit=True)
    raw.execute("INSERT INTO sites (name) VALUES ('SiteA')")
    raw.close()
    result = upgrade(db_path, migrations=[M1], latest=2, now=NOW)
    raw = sqlite3.connect(result.backup_path)
    assert raw.execute("SELECT name FROM sites").fetchall() == [("SiteA",)]
    raw.close()


def test_failed_step_leaves_last_good_version(db_path):
    bad = Migration(2, "broken", fail_after("extra_bad"))
    with pytest.raises(MigrationError, match="database is at version 2") as exc:
        upgrade(db_path, migrations=[M1, bad], latest=3, now=NOW)
    assert "Backup:" in str(exc.value)
    assert user_version(db_path) == 2
    cols = columns(db_path, "recordings")
    assert "extra_a" in cols
    assert "extra_bad" not in cols
    assert user_version(db_path.with_name("catalog.v1-backup-20261002T030405Z.db")) == 1


def test_failed_first_step_leaves_version_unchanged(db_path):
    bad = Migration(1, "broken", fail_after("extra_bad"))
    with pytest.raises(MigrationError, match="database is at version 1"):
        upgrade(db_path, migrations=[bad], latest=2, now=NOW)
    assert user_version(db_path) == 1
    assert "extra_bad" not in columns(db_path, "recordings")


def test_incomplete_chain_is_refused_before_backup(db_path):
    before = files_in(db_path.parent)
    with pytest.raises(MigrationError, match="no migration from schema version 2"):
        upgrade(db_path, migrations=[M1], latest=3, now=NOW)
    assert files_in(db_path.parent) == before
    assert user_version(db_path) == 1


def test_newer_database_is_refused(db_path):
    with pytest.raises(SchemaVersionError):
        upgrade(db_path, migrations=[], latest=0, now=NOW)


def test_foreign_database_is_refused(tmp_path):
    path = tmp_path / "other.db"
    raw = sqlite3.connect(path, autocommit=True)
    raw.execute("CREATE TABLE legacy (date TEXT)")
    raw.close()
    with pytest.raises(SchemaVersionError):
        upgrade(path, migrations=[M1], latest=2, now=NOW)
    assert files_in(tmp_path) == ["other.db"]


def test_existing_backup_is_never_overwritten(db_path):
    taken = db_path.with_name("catalog.v1-backup-20261002T030405Z.db")
    taken.write_bytes(b"older backup")
    with pytest.raises(FileExistsError):
        upgrade(db_path, migrations=[M1], latest=2, now=NOW)
    assert taken.read_bytes() == b"older backup"
    assert user_version(db_path) == 1


def test_upgraded_database_opens_normally(db_path, monkeypatch):
    monkeypatch.setattr(version, "LATEST_VERSION", 2)
    with pytest.raises(SchemaVersionError):
        connect(db_path)
    upgrade(db_path, migrations=[M1], now=NOW)
    with open_db(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2


# ---------------------------------------------------------------------------
# Foreign keys during migration
# ---------------------------------------------------------------------------


def test_disable_foreign_keys_step(db_path):
    seen = []

    def apply(conn: sqlite3.Connection) -> None:
        seen.append(conn.execute("PRAGMA foreign_keys").fetchone()[0])
        conn.execute("ALTER TABLE sites ADD COLUMN extra TEXT")

    upgrade(db_path, migrations=[Migration(1, "fk off", apply, True)], latest=2, now=NOW)
    assert seen == [0]
    assert user_version(db_path) == 2


def test_foreign_key_violation_rolls_back_step(db_path):
    def orphan(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO channels (recording_id, channel_index, fc_hz, fs_hz, start_unix,"
            " end_unix) VALUES (999, 0, 1, 1, 0, 1)"
        )

    step = Migration(1, "orphan", orphan, disable_foreign_keys=True)
    with pytest.raises(MigrationError, match="foreign key check failed"):
        upgrade(db_path, migrations=[step], latest=2, now=NOW)
    assert user_version(db_path) == 1
    raw = sqlite3.connect(db_path)
    assert raw.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == 0
    raw.close()


# ---------------------------------------------------------------------------
# backup_database
# ---------------------------------------------------------------------------


def test_backup_database_name_and_content(db_path):
    path = backup_database(db_path, 1, NOW)
    assert path.name == "catalog.v1-backup-20261002T030405Z.db"
    assert user_version(path) == 1


def test_backup_database_detects_version_mismatch(db_path):
    with pytest.raises(MigrationError, match="failed verification"):
        backup_database(db_path, 7, NOW)
