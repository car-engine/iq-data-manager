"""Constraints, triggers and cascades in schema.sql, tested with plain sqlite3."""

import sqlite3
from importlib import resources

import pytest

SCHEMA = resources.files("iqdm.db").joinpath("schema.sql").read_text(encoding="utf-8")


@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(tmp_path / "schema_test.db", autocommit=True)
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript(SCHEMA)
    yield c
    c.close()


def add_site(conn, name="SiteA") -> int:
    return conn.execute("INSERT INTO sites (name) VALUES (?) RETURNING id", (name,)).fetchone()[0]


def add_recording(conn, site_id=None, rel_path="rec1", **overrides) -> int:
    row = {
        "logged_by": "tester",
        "date": "2026-09-30T02:00:00Z",
        "start_unix": 1790733600.0,
        "end_unix": 1790733610.0,
        "site_id": site_id if site_id is not None else add_site(conn, f"site-{rel_path}"),
        "storage_root": "C:/captures",
        "rel_path": rel_path,
    } | overrides
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    sql = f"INSERT INTO recordings ({cols}) VALUES ({marks}) RETURNING id"  # noqa: S608
    return conn.execute(sql, tuple(row.values())).fetchone()[0]


def add_channel(conn, recording_id, index=0) -> int:
    return conn.execute(
        "INSERT INTO channels (recording_id, channel_index, sub_path, fc_hz, fs_hz,"
        " start_unix, end_unix) VALUES (?, ?, ?, 100e6, 1000, 1790733600, 1790733610)"
        " RETURNING id",
        (recording_id, index, str(index)),
    ).fetchone()[0]


def add_param(conn, recording_id, channel_id=None, param="SDR", value="X310") -> int:
    return conn.execute(
        "INSERT INTO recording_params (recording_id, channel_id, param, value)"
        " VALUES (?, ?, ?, ?) RETURNING id",
        (recording_id, channel_id, param, value),
    ).fetchone()[0]


def add_transfer(conn, recording_id, **overrides) -> int:
    row = {
        "recording_id": recording_id,
        "operation": "copy",
        "source": "C:/captures/rec1",
        "destination": "D:/work/rec1",
        "started_at": "2026-10-02T00:00:00Z",
        "performed_by": "tester",
    } | overrides
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    sql = f"INSERT INTO transfer_log ({cols}) VALUES ({marks}) RETURNING id"  # noqa: S608
    return conn.execute(sql, tuple(row.values())).fetchone()[0]


def count(conn, table) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_version_and_tables(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")}
    assert tables == {"sites", "recordings", "channels", "recording_params", "transfer_log"}


def test_defaults(conn):
    rid = add_recording(conn)
    row = conn.execute(
        "SELECT dtype, iq_layout, endianness, header_bytes, archive_state, file_duration_s"
        " FROM recordings WHERE id = ?",
        (rid,),
    ).fetchone()
    assert row == ("int16", "interleaved_iq", "little", 0, "local", 1.0)


# ---------------------------------------------------------------------------
# CHECK constraints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dtype", ["int8", "int16", "float32"])
def test_dtype_allowed(conn, dtype):
    add_recording(conn, dtype=dtype)


@pytest.mark.parametrize("dtype", ["uint8", "int32", "sc16", "INT16", ""])
def test_dtype_rejected(conn, dtype):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        add_recording(conn, dtype=dtype)


@pytest.mark.parametrize(
    "overrides",
    [
        {"iq_layout": "planar_qi"},
        {"endianness": "middle"},
        {"header_bytes": -1},
        {"file_duration_s": 0},
        {"start_unix": 10.0, "end_unix": 9.0},
        {"archive_state": "deleted"},
    ],
)
def test_recording_checks(conn, overrides):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        add_recording(conn, **overrides)


def test_archived_needs_archived_at(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        add_recording(conn, rel_path="a", archive_state="archived")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        add_recording(conn, rel_path="b", archived_at="2026-10-02T00:00:00Z")
    add_recording(conn, rel_path="c", archive_state="archived", archived_at="2026-10-02T00:00:00Z")


def test_channel_checks(conn):
    rid = add_recording(conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        add_channel(conn, rid, index=-1)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute(
            "INSERT INTO channels (recording_id, channel_index, fc_hz, fs_hz, start_unix,"
            " end_unix) VALUES (?, 0, 1, 0, 0, 1)",
            (rid,),
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"operation": "delete"},
        {"operation": "archive"},
        {"verification": "ok"},
        {"hash_mode": "some"},
        {"channels": ""},
        {"channels": "a"},
        {"channels": "0;2"},
        {"channels": "0, 2"},
        {"range_start_unix": 10.0, "range_end_unix": 5.0},
    ],
)
def test_transfer_checks(conn, overrides):
    rid = add_recording(conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        add_transfer(conn, rid, **overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"channels": "0"},
        {"channels": "0,2,10"},
        {"hash_mode": "none"},
        {"hash_mode": "sample"},
        {"hash_mode": "all"},
        {"operation": "check", "destination": None, "verification": "skipped"},
    ],
)
def test_transfer_valid(conn, overrides):
    rid = add_recording(conn)
    add_transfer(conn, rid, **overrides)


# ---------------------------------------------------------------------------
# Delete rows and manifests (DECISIONS.md D52)
# ---------------------------------------------------------------------------


def passed_move(conn, rid) -> int:
    return add_transfer(conn, rid, operation="move", verification="pass")


def add_delete(conn, rid, parent_id) -> int:
    return add_transfer(conn, rid, operation="delete", parent_id=parent_id, destination=None)


def test_delete_after_a_passed_move_is_accepted(conn):
    rid = add_recording(conn)
    add_delete(conn, rid, passed_move(conn, rid))
    assert count(conn, "transfer_log") == 2


@pytest.mark.parametrize(
    "parent",
    [
        {"operation": "move", "verification": "fail"},
        {"operation": "move", "verification": "skipped"},
        {"operation": "copy", "verification": "pass"},
        {"operation": "check", "verification": "pass", "destination": None},
    ],
)
def test_delete_needs_a_passed_move_as_parent(conn, parent):
    rid = add_recording(conn)
    parent_id = add_transfer(conn, rid, **parent)
    with pytest.raises(sqlite3.IntegrityError, match="passed move"):
        add_delete(conn, rid, parent_id)


def test_delete_parent_must_exist(conn):
    rid = add_recording(conn)
    with pytest.raises(sqlite3.IntegrityError, match="passed move"):
        add_delete(conn, rid, 999)


def test_delete_parent_must_belong_to_the_same_recording(conn):
    rid = add_recording(conn)
    other = add_recording(conn, rel_path="rec2")
    with pytest.raises(sqlite3.IntegrityError, match="passed move"):
        add_delete(conn, other, passed_move(conn, rid))


def test_parent_id_only_on_a_delete_row(conn):
    rid = add_recording(conn)
    move = passed_move(conn, rid)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        add_transfer(conn, rid, parent_id=move)


def test_delete_row_cannot_be_moved_to_a_failed_parent(conn):
    rid = add_recording(conn)
    delete = add_delete(conn, rid, passed_move(conn, rid))
    failed = add_transfer(conn, rid, operation="move", verification="fail")
    with pytest.raises(sqlite3.IntegrityError, match="passed move"):
        conn.execute("UPDATE transfer_log SET parent_id = ? WHERE id = ?", (failed, delete))


def test_row_cannot_become_a_delete_of_a_failed_move(conn):
    rid = add_recording(conn)
    failed = add_transfer(conn, rid, operation="move", verification="fail")
    copy = add_transfer(conn, rid)
    with pytest.raises(sqlite3.IntegrityError, match="passed move"):
        conn.execute(
            "UPDATE transfer_log SET operation = 'delete', parent_id = ? WHERE id = ?",
            (failed, copy),
        )


def test_manifest_columns(conn):
    rid = add_recording(conn)
    digest = "0123456789abcdef" * 4
    tid = add_transfer(conn, rid, manifest_path="C:/m/transfer-1.json", manifest_sha256=digest)
    row = conn.execute(
        "SELECT manifest_path, manifest_sha256 FROM transfer_log WHERE id = ?", (tid,)
    ).fetchone()
    assert row == ("C:/m/transfer-1.json", digest)


@pytest.mark.parametrize("digest", ["abc", "0123456789ABCDEF" * 4, "g" * 64, "0" * 65])
def test_manifest_sha256_must_be_lower_case_hex(conn, digest):
    rid = add_recording(conn)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        add_transfer(conn, rid, manifest_sha256=digest)


# ---------------------------------------------------------------------------
# Uniqueness
# ---------------------------------------------------------------------------


def test_site_names_unique_ignoring_case(conn):
    add_site(conn, "LocationA")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        add_site(conn, "locationa")


def test_location_unique(conn):
    sid = add_site(conn)
    add_recording(conn, site_id=sid, rel_path="same")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        add_recording(conn, site_id=sid, rel_path="same")


def test_channel_index_unique_per_recording(conn):
    rid = add_recording(conn)
    add_channel(conn, rid, 0)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        add_channel(conn, rid, 0)


# ---------------------------------------------------------------------------
# Foreign keys and cascades
# ---------------------------------------------------------------------------


def test_recording_delete_cascades_to_channels_and_params(conn):
    rid = add_recording(conn)
    cid = add_channel(conn, rid)
    add_param(conn, rid)
    add_param(conn, rid, channel_id=cid, param="Antenna", value="Discone")
    conn.execute("DELETE FROM recordings WHERE id = ?", (rid,))
    assert count(conn, "channels") == 0
    assert count(conn, "recording_params") == 0


def test_channel_delete_cascades_to_its_params_only(conn):
    rid = add_recording(conn)
    c0 = add_channel(conn, rid, 0)
    c1 = add_channel(conn, rid, 1)
    add_param(conn, rid)
    add_param(conn, rid, channel_id=c0, param="Antenna")
    add_param(conn, rid, channel_id=c1, param="Antenna")
    conn.execute("DELETE FROM channels WHERE id = ?", (c1,))
    remaining = conn.execute("SELECT channel_id FROM recording_params ORDER BY id").fetchall()
    assert remaining == [(None,), (c0,)]


def test_transfer_history_blocks_recording_delete(conn):
    rid = add_recording(conn)
    add_transfer(conn, rid)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute("DELETE FROM recordings WHERE id = ?", (rid,))


def test_recording_needs_existing_site(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        add_recording(conn, site_id=999)


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------


def test_param_channel_must_belong_to_same_recording(conn):
    r1 = add_recording(conn, rel_path="r1")
    r2 = add_recording(conn, rel_path="r2")
    c1 = add_channel(conn, r1)
    c2 = add_channel(conn, r2)
    add_param(conn, r1, channel_id=c1)
    with pytest.raises(sqlite3.IntegrityError, match="different recording"):
        add_param(conn, r1, channel_id=c2)


def test_param_channel_update_is_checked(conn):
    r1 = add_recording(conn, rel_path="r1")
    r2 = add_recording(conn, rel_path="r2")
    c1 = add_channel(conn, r1)
    c2 = add_channel(conn, r2)
    pid = add_param(conn, r1, channel_id=c1)
    with pytest.raises(sqlite3.IntegrityError, match="different recording"):
        conn.execute("UPDATE recording_params SET channel_id = ? WHERE id = ?", (c2, pid))
    with pytest.raises(sqlite3.IntegrityError, match="different recording"):
        conn.execute("UPDATE recording_params SET recording_id = ? WHERE id = ?", (r2, pid))
    conn.execute("UPDATE recording_params SET channel_id = NULL WHERE id = ?", (pid,))


def test_param_with_missing_channel_is_rejected(conn):
    rid = add_recording(conn)
    with pytest.raises(sqlite3.IntegrityError):
        add_param(conn, rid, channel_id=999)


def test_updated_at_trigger(conn):
    old = "2000-01-01T00:00:00Z"
    rid = add_recording(conn, created_at=old, updated_at=old)
    conn.execute("UPDATE recordings SET remarks = 'x' WHERE id = ?", (rid,))
    created, updated = conn.execute(
        "SELECT created_at, updated_at FROM recordings WHERE id = ?", (rid,)
    ).fetchone()
    assert created == old
    assert updated != old
    assert updated.endswith("Z")


def test_updated_at_explicit_value_is_kept(conn):
    rid = add_recording(conn)
    conn.execute(
        "UPDATE recordings SET remarks = 'x', updated_at = '2030-01-01T00:00:00Z' WHERE id = ?",
        (rid,),
    )
    assert conn.execute("SELECT updated_at FROM recordings").fetchone()[0] == (
        "2030-01-01T00:00:00Z"
    )
