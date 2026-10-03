"""Tests for the legacy import end to end: iqdm.db.legacy and the command (D66).

Each test builds a synthetic legacy database under tmp_path with sqlite3, in the
legacy table layout. The real legacy file is never read.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

import migrate_legacy
from iqdm import legacy
from iqdm.check_main import main as check_main
from iqdm.db import repository
from iqdm.db.connection import DatabaseError, open_db
from iqdm.db.legacy import LEGACY_COLUMNS, LegacyFormatError, read_legacy_rows, write_import
from iqdm.legacy import REPORT_SUFFIX, main
from iqdm.models import IN_PLACE_NOTE, ArchiveState, Operation, Verification

ROOT = "\\\\nas\\Data\\IQ"
START = datetime(2026, 9, 18, 3, 0, tzinfo=UTC).timestamp()
LEGACY_TABLE = (
    "CREATE TABLE {name} (date TEXT, date_unix REAL, site TEXT, band TEXT, fc_hz REAL,"
    " fs_hz REAL, duration_s INTEGER, data_dir TEXT, remarks TEXT)"
)


def legacy_row(data_dir: str, **kw: object) -> dict[str, object]:
    values: dict[str, object] = {
        "date": "2026-09-18 11:00:00",
        "date_unix": START,
        "site": "LocationA",
        "band": "VHF",
        "fc_hz": 145.8e6,
        "fs_hz": 1e6,
        "duration_s": 600,
        "data_dir": data_dir,
        "remarks": None,
    }
    values.update(kw)
    return values


def make_legacy(path: Path, rows: list[dict[str, object]], *, table: str = "iq_log") -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.execute(LEGACY_TABLE.format(name=table))
        conn.executemany(
            f"INSERT INTO {table} ({', '.join(LEGACY_COLUMNS)})"  # noqa: S608
            f" VALUES ({', '.join('?' for _ in LEGACY_COLUMNS)})",
            [tuple(r[c] for c in LEGACY_COLUMNS) for r in rows],
        )
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture
def legacy_db(tmp_path) -> Path:
    return make_legacy(
        tmp_path / "legacy.db",
        [
            legacy_row(f"{ROOT}\\recording1\\0\\"),
            legacy_row(f"{ROOT}\\recording1\\1\\", band="UHF", fc_hz=433.92e6),
            legacy_row(f"{ROOT}\\recording2\\", site="LocationB", remarks="calm"),
            legacy_row("D:\\data\\recording3\\0\\"),
        ],
    )


def snapshot(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_mtime_ns


# =========================================================================
# Reading the legacy file
# =========================================================================


def test_rows_are_read_in_rowid_order(legacy_db):
    table, rows = read_legacy_rows(legacy_db)
    assert table == "iq_log"
    assert [r.row for r in rows] == [1, 2, 3, 4]
    assert rows[1].data_dir == f"{ROOT}\\recording1\\1\\"
    assert rows[1].fc_hz == 433.92e6
    assert rows[2].remarks == "calm"
    assert rows[0].remarks is None


def test_reading_changes_nothing_in_the_legacy_file(legacy_db):
    before = snapshot(legacy_db)
    read_legacy_rows(legacy_db)
    assert snapshot(legacy_db) == before
    assert sorted(p.name for p in legacy_db.parent.iterdir()) == ["legacy.db"]


def test_two_tables_need_a_table_name(legacy_db):
    conn = sqlite3.connect(legacy_db)
    conn.execute("CREATE TABLE notes (text TEXT)")
    conn.close()
    with pytest.raises(LegacyFormatError, match=r"2 tables .*iq_log, notes.*--table"):
        read_legacy_rows(legacy_db)
    table, rows = read_legacy_rows(legacy_db, "iq_log")
    assert (table, len(rows)) == ("iq_log", 4)
    with pytest.raises(LegacyFormatError, match="no table named 'log'"):
        read_legacy_rows(legacy_db, "log")


def test_a_missing_column_is_refused(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE iq_log (date TEXT, date_unix REAL, site TEXT, data_dir TEXT)")
    conn.close()
    with pytest.raises(LegacyFormatError, match="lacks the columns: band, fc_hz, fs_hz"):
        read_legacy_rows(path)


def test_column_names_match_without_letter_case(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(LEGACY_TABLE.upper().replace("{NAME}", "IQ_LOG"))
    conn.execute("INSERT INTO IQ_LOG (DATA_DIR) VALUES ('x')")
    conn.commit()
    conn.close()
    _, [row] = read_legacy_rows(path)
    assert row.data_dir == "x"


def test_a_missing_or_foreign_file_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_legacy_rows(tmp_path / "none.db")
    text = tmp_path / "notes.db"
    text.write_text("not a database", encoding="utf-8")
    with pytest.raises(LegacyFormatError, match="cannot read the legacy database"):
        read_legacy_rows(text)


# =========================================================================
# Writing the import
# =========================================================================


def test_write_import_rolls_back_on_an_error(db_path):
    plan = legacy.build_plan(
        read_legacy_rows(make_legacy(db_path.parent / "old.db", [legacy_row(f"{ROOT}\\r\\0")]))[1],
        [ROOT],
        now="2026-10-04T08:00:00Z",
    )
    with pytest.raises(KeyError):  # a recording whose site is not in the list
        write_import(db_path, [], plan.recordings, performed_by="t", at="2026-10-04T08:00:00Z")
    with open_db(db_path, readonly=True) as conn:
        assert repository.list_recordings(conn) == []
        assert repository.list_sites(conn) == []


# =========================================================================
# The command
# =========================================================================


def run(legacy_db: Path, new: Path, *extra: str) -> int:
    return main([str(legacy_db), str(new), "--nas-root", ROOT, *extra])


def test_import_writes_recordings_sites_and_the_report(legacy_db, tmp_path, capsys):
    new = tmp_path / "catalog.db"
    before = snapshot(legacy_db)
    assert run(legacy_db, new) == 0
    assert snapshot(legacy_db) == before
    out = capsys.readouterr().out
    assert "Recordings:        2 (3 channels)" in out
    assert "row 4: D:\\data\\recording3\\0\\: not under any NAS root" in out
    assert f"Wrote 2 recordings to {new}." in out

    report = new.with_name(new.name + REPORT_SUFFIX)
    assert report.name == "catalog.db.report.txt"
    text = report.read_text(encoding="utf-8")
    assert "Rows not imported: 1" in text
    assert text in out

    with open_db(new, readonly=True) as conn:
        assert [s.name for s in repository.list_sites(conn)] == ["LocationA", "LocationB"]
        summaries = repository.list_recordings(conn)
        assert len(summaries) == 2
        assert all(s.unverified for s in summaries)  # "archived, not verified" (D2, D44)
        assert all(s.archive_state is ArchiveState.ARCHIVED for s in summaries)
        assert {s.logged_by for s in summaries} == {"legacy-import"}
        recording_id = repository.find_recording_by_location(conn, ROOT, "recording1")
        assert recording_id is not None
        full = repository.get_recording(conn, recording_id)
        assert [c.channel_index for c in full.channels] == [0, 1]
        assert (full.start_unix, full.end_unix) == (START, START + 600)
        assert full.date == "2026-09-18T03:00:00Z"
        [row] = repository.list_transfers(conn, recording_id)
        assert row.operation is Operation.CHECK
        assert row.verification is Verification.SKIPPED
        assert row.notes == IN_PLACE_NOTE
        assert row.source == f"{ROOT}\\recording1"
        assert row.performed_by == "legacy-import"
        assert row.started_at == row.finished_at == full.archived_at


def test_dry_run_writes_nothing(legacy_db, tmp_path, capsys):
    new = tmp_path / "catalog.db"
    assert run(legacy_db, new, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "Recordings:        2 (3 channels)" in out
    assert out.rstrip().endswith("Dry run: nothing written.")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["legacy.db"]


def test_an_existing_new_database_is_refused(legacy_db, tmp_path, capsys):
    new = tmp_path / "catalog.db"
    new.write_bytes(b"keep me")
    assert run(legacy_db, new) == 1
    assert "refusing to write over an existing file" in capsys.readouterr().err
    assert new.read_bytes() == b"keep me"
    assert run(legacy_db, new, "--dry-run") == 1


def test_an_existing_report_is_refused(legacy_db, tmp_path, capsys):
    new = tmp_path / "catalog.db"
    report = tmp_path / "catalog.db.report.txt"
    report.write_text("keep me", encoding="utf-8")
    assert run(legacy_db, new) == 1
    assert "catalog.db.report.txt" in capsys.readouterr().err
    assert not new.exists()
    assert report.read_text(encoding="utf-8") == "keep me"


def test_the_legacy_file_cannot_be_the_new_database(legacy_db, capsys):
    before = snapshot(legacy_db)
    assert run(legacy_db, legacy_db) == 1
    assert "cannot be the legacy file" in capsys.readouterr().err
    assert snapshot(legacy_db) == before


def test_nothing_importable_writes_nothing(tmp_path, capsys):
    old = make_legacy(tmp_path / "old.db", [legacy_row("D:\\data\\rec\\0")])
    new = tmp_path / "catalog.db"
    assert run(old, new) == 1
    assert "no recording can be imported; nothing written" in capsys.readouterr().err
    assert not new.exists()


def test_a_failed_import_names_the_file(legacy_db, tmp_path, monkeypatch, capsys):
    def fail(*_a: object, **_k: object) -> None:
        raise DatabaseError("disk full")

    monkeypatch.setattr(legacy, "write_import", fail)
    new = tmp_path / "catalog.db"
    assert run(legacy_db, new) == 1
    err = capsys.readouterr().err
    assert "the import failed: disk full" in err
    assert f"The file {new} may remain with an empty schema" in err
    assert not new.with_name(new.name + REPORT_SUFFIX).exists()


def test_a_table_error_is_reported(legacy_db, tmp_path, capsys):
    assert run(legacy_db, tmp_path / "catalog.db", "--table", "log") == 1
    assert "no table named 'log'" in capsys.readouterr().err


def test_mapped_drives_from_the_command_line(tmp_path):
    old = make_legacy(tmp_path / "old.db", [legacy_row("Z:\\IQ\\recording1\\0")])
    new = tmp_path / "catalog.db"
    assert run(old, new, "--drive", "Z:=\\\\nas\\Data") == 0
    with open_db(new, readonly=True) as conn:
        assert repository.find_recording_by_location(conn, ROOT, "recording1") is not None


@pytest.mark.parametrize(
    "extra",
    [
        ["--nas-root", "D:\\data"],
        ["--drive", "Z:"],
    ],
)
def test_wrong_arguments_are_a_usage_error(legacy_db, tmp_path, extra, capsys):
    with pytest.raises(SystemExit) as exc:
        run(legacy_db, tmp_path / "catalog.db", *extra)
    assert exc.value.code == 2
    assert capsys.readouterr().err
    assert not (tmp_path / "catalog.db").exists()


def test_a_nas_root_is_required(legacy_db, tmp_path):
    with pytest.raises(SystemExit):
        main([str(legacy_db), str(tmp_path / "catalog.db")])


def test_the_console_program_runs_the_import(legacy_db, tmp_path, capsys):
    new = tmp_path / "catalog.db"
    assert check_main(["migrate-legacy", str(legacy_db), str(new), "--nas-root", ROOT]) == 0
    assert new.is_file()
    assert check_main(["migrate-legacy", "--help"]) == 0
    assert "usage: IQDataManager-check.exe migrate-legacy" in capsys.readouterr().out


def test_the_tool_script_is_the_package_module():
    assert migrate_legacy is legacy
