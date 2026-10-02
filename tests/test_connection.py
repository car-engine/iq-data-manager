"""Tests for iqdm.db.connection and iqdm.db.version. All databases live in tmp_path."""

import sqlite3
import sys

import pytest

from iqdm.db import connection, version
from iqdm.db.connection import (
    DatabaseBusyError,
    SchemaVersionError,
    connect,
    connection_settings,
    create_database,
    database_status,
    inspect_database,
    open_db,
    sqlite_uri,
    write_transaction,
)
from iqdm.db.version import SchemaStatus

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows path forms")


def set_user_version(path, value: int) -> None:
    raw = sqlite3.connect(path, autocommit=True)
    raw.execute(f"PRAGMA user_version = {value}")
    raw.close()


def site_count(path) -> int:
    with open_db(path, readonly=True) as conn:
        return conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]


# ---------------------------------------------------------------------------
# URIs (string checks only; no network access)
# ---------------------------------------------------------------------------


@windows_only
def test_uri_for_drive_path():
    assert sqlite_uri(r"C:\data\iq_catalog.db", "ro") == "file:///C:/data/iq_catalog.db?mode=ro"


@windows_only
def test_uri_for_unc_path():
    assert (
        sqlite_uri(r"\\nas\recordings\iq_catalog.db", "rw")
        == "file:////nas/recordings/iq_catalog.db?mode=rw"
    )


@windows_only
def test_uri_escapes_special_characters():
    assert (
        sqlite_uri(r"C:\a b\#1%x.db", "rwc") == "file:///C:/a%20b/%231%25x.db?mode=rwc"
    )


def test_uri_rejects_unknown_mode():
    with pytest.raises(ValueError, match="mode"):
        sqlite_uri("x.db", "memory")


def test_create_and_open_path_with_special_characters(tmp_path):
    path = tmp_path / "a b #1 %x" / "catalog.db"
    path.parent.mkdir()
    create_database(path)
    with open_db(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# create_database, connect, open_db
# ---------------------------------------------------------------------------


def test_create_database(db_path):
    assert database_status(db_path) is SchemaStatus.CURRENT
    with open_db(db_path, readonly=True) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    assert "recordings" in tables


def test_create_database_refuses_existing_file(tmp_path):
    path = tmp_path / "existing.db"
    path.write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        create_database(path)
    assert path.read_bytes() == b"keep me"


def test_connect_refuses_missing_file_and_creates_nothing(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        connect(path)
    with pytest.raises(FileNotFoundError):
        connect(path, readonly=True)
    assert not path.exists()


def test_pragmas(db_path):
    with open_db(db_path) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert conn.autocommit is True
        assert not conn.in_transaction


def test_connection_settings(db_path):
    with open_db(db_path) as conn:
        assert connection_settings(conn) == {
            "journal_mode": "delete",
            "foreign_keys": 1,
            "busy_timeout": 5000,
        }
    with open_db(db_path, readonly=True) as conn:
        assert connection_settings(conn)["foreign_keys"] == 1


def test_wal_is_switched_back_to_delete(db_path):
    raw = sqlite3.connect(db_path, autocommit=True)
    assert raw.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    raw.close()
    with open_db(db_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"


def test_readonly_connection_cannot_write(db_path):
    with open_db(db_path, readonly=True) as conn, pytest.raises(
        sqlite3.OperationalError, match="readonly"
    ):
        conn.execute("INSERT INTO sites (name) VALUES ('x')")


def test_open_db_closes_connection(db_path):
    with open_db(db_path) as conn:
        pass
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")


def test_open_db_closes_connection_on_error(db_path):
    with pytest.raises(RuntimeError), open_db(db_path) as conn:
        raise RuntimeError("boom")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")


# ---------------------------------------------------------------------------
# Schema version rules (DECISIONS.md D6)
# ---------------------------------------------------------------------------


def test_newer_database_is_readable_but_not_writable(db_path):
    set_user_version(db_path, 2)
    assert database_status(db_path) is SchemaStatus.TOO_NEW
    with open_db(db_path, readonly=True) as conn:
        conn.execute("SELECT COUNT(*) FROM recordings")
    with pytest.raises(SchemaVersionError, match="newer version") as exc:
        connect(db_path)
    assert exc.value.status is SchemaStatus.TOO_NEW


def test_older_database_is_refused(db_path, monkeypatch):
    monkeypatch.setattr(version, "LATEST_VERSION", 2)
    assert database_status(db_path) is SchemaStatus.NEEDS_UPGRADE
    for readonly in (False, True):
        with pytest.raises(SchemaVersionError, match="older schema"):
            connect(db_path, readonly=readonly)


def test_foreign_database_is_refused(tmp_path):
    path = tmp_path / "other.db"
    raw = sqlite3.connect(path, autocommit=True)
    raw.execute("CREATE TABLE legacy (date TEXT)")
    raw.close()
    assert database_status(path) is SchemaStatus.NOT_IQDM
    for readonly in (False, True):
        with pytest.raises(SchemaVersionError, match="not an IQ Data Manager"):
            connect(path, readonly=readonly)


# ---------------------------------------------------------------------------
# inspect_database (Settings tab status line)
# ---------------------------------------------------------------------------


def test_inspect_current_database(db_path):
    info = inspect_database(db_path)
    assert info.found
    assert info.error is None
    assert info.user_version == 1
    assert info.latest_version == 1
    assert info.status is SchemaStatus.CURRENT
    assert info.settings == {"journal_mode": "delete", "foreign_keys": 1, "busy_timeout": 5000}


def test_inspect_newer_database(db_path):
    set_user_version(db_path, 3)
    info = inspect_database(db_path)
    assert (info.user_version, info.status) == (3, SchemaStatus.TOO_NEW)


def test_inspect_older_database(db_path, monkeypatch):
    monkeypatch.setattr(version, "LATEST_VERSION", 2)
    info = inspect_database(db_path)
    assert (info.user_version, info.latest_version) == (1, 2)
    assert info.status is SchemaStatus.NEEDS_UPGRADE


def test_inspect_sqlite_file_that_is_not_ours(tmp_path):
    path = tmp_path / "other.db"
    raw = sqlite3.connect(path, autocommit=True)
    raw.execute("CREATE TABLE legacy (date TEXT)")
    raw.close()
    info = inspect_database(path)
    assert (info.user_version, info.status) == (0, SchemaStatus.NOT_IQDM)


def test_inspect_file_that_is_not_a_database(tmp_path):
    path = tmp_path / "notes.db"
    path.write_bytes(b"this is not an SQLite file" * 100)
    info = inspect_database(path)
    assert info.found
    assert info.status is None
    assert "Cannot read the file as an SQLite database" in info.error


def test_inspect_missing_file_creates_nothing(tmp_path):
    path = tmp_path / "absent.db"
    info = inspect_database(path)
    assert not info.found
    assert info.error == "The file was not found."
    assert not path.exists()


def test_inspect_folder(tmp_path):
    info = inspect_database(tmp_path)
    assert not info.found
    assert info.error == "The file is a folder."


def test_inspect_changes_nothing(db_path):
    before = (db_path.read_bytes(), db_path.stat().st_mtime_ns)
    inspect_database(db_path)
    assert (db_path.read_bytes(), db_path.stat().st_mtime_ns) == before
    assert sorted(p.name for p in db_path.parent.iterdir()) == ["catalog.db"]


# ---------------------------------------------------------------------------
# write_transaction
# ---------------------------------------------------------------------------


@pytest.fixture
def short_busy_timeout(monkeypatch):
    """Keep lock tests fast: wait 50 ms inside SQLite instead of 5 s."""
    monkeypatch.setattr(connection, "BUSY_TIMEOUT_MS", 50)


@pytest.fixture
def blocker(db_path):
    """A second connection that holds the write lock until released."""
    raw = sqlite3.connect(db_path, autocommit=True)
    raw.execute("BEGIN IMMEDIATE")
    yield raw
    if raw.in_transaction:
        raw.execute("ROLLBACK")
    raw.close()


def add_site(conn: sqlite3.Connection) -> int:
    return conn.execute("INSERT INTO sites (name) VALUES ('A') RETURNING id").fetchone()[0]


def test_write_transaction_commits_and_returns(db_path):
    assert write_transaction(db_path, add_site) == 1
    assert site_count(db_path) == 1


def test_write_transaction_rolls_back_on_error(db_path):
    sleeps = []

    def fails(conn):
        add_site(conn)
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        write_transaction(db_path, fails, sleep=sleeps.append)
    assert site_count(db_path) == 0
    assert sleeps == []


def test_write_transaction_does_not_retry_other_sql_errors(db_path):
    sleeps = []
    with pytest.raises(sqlite3.OperationalError, match="syntax"):
        write_transaction(db_path, lambda c: c.execute("SELEC 1"), sleep=sleeps.append)
    assert sleeps == []


def test_write_transaction_gives_up_after_all_attempts(db_path, short_busy_timeout, blocker):
    sleeps = []
    calls = []

    def fn(conn):
        calls.append(1)
        return add_site(conn)

    with pytest.raises(DatabaseBusyError, match="Tried 3 times"):
        write_transaction(db_path, fn, sleep=sleeps.append)
    assert sleeps == [1.0, 2.0]
    assert calls == []  # BEGIN IMMEDIATE failed each time, so fn never ran
    blocker.execute("ROLLBACK")
    assert site_count(db_path) == 0


def test_write_transaction_succeeds_when_lock_is_released(db_path, short_busy_timeout, blocker):
    sleeps = []

    def release_then_record(seconds: float) -> None:
        sleeps.append(seconds)
        blocker.execute("ROLLBACK")

    assert write_transaction(db_path, add_site, sleep=release_then_record) == 1
    assert sleeps == [1.0]
    assert site_count(db_path) == 1


def test_write_transaction_custom_delays(db_path, short_busy_timeout, blocker):
    sleeps = []
    with pytest.raises(DatabaseBusyError, match="Tried 2 times"):
        write_transaction(db_path, add_site, delays=[0.1], sleep=sleeps.append)
    assert sleeps == [0.1]


def test_write_transaction_refuses_newer_schema(db_path):
    set_user_version(db_path, 2)
    with pytest.raises(SchemaVersionError):
        write_transaction(db_path, add_site)


def test_verify_schema_in_memory():
    assert connection.verify_schema_in_memory() == version.LATEST_VERSION
