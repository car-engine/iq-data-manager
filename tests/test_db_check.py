"""Tests for tools/db_check.py (open item O21). All databases live in tmp_path.

The locking tests start the tool as separate processes, as on two PCs.
"""

import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

import db_check
from iqdm.db.connection import database_status
from iqdm.db.version import SchemaStatus

TOOL = Path(__file__).resolve().parents[1] / "tools" / "db_check.py"


def run(capsys, *argv: str) -> tuple[int, str]:
    code = db_check.main(list(argv))
    return code, capsys.readouterr().out


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create_makes_a_current_database(tmp_path, capsys):
    path = tmp_path / "test.db"
    code, out = run(capsys, "create", str(path))
    assert code == 0
    assert "PASS  create database" in out
    assert "PASS  schema version: current" in out
    assert out.rstrip().endswith("RESULT PASS")
    assert database_status(path) is SchemaStatus.CURRENT


def test_create_refuses_an_existing_file(tmp_path, capsys):
    path = tmp_path / "test.db"
    path.write_bytes(b"keep me")
    code, out = run(capsys, "create", str(path))
    assert code == 1
    assert "FAIL  create database: FileExistsError" in out
    assert path.read_bytes() == b"keep me"


def test_create_in_a_missing_folder_fails(tmp_path, capsys):
    code, out = run(capsys, "create", str(tmp_path / "missing" / "test.db"))
    assert code == 1
    assert "FAIL  create database" in out


# ---------------------------------------------------------------------------
# check and write
# ---------------------------------------------------------------------------


def test_check_passes_and_can_repeat(db_path, capsys):
    for _ in range(2):
        code, out = run(capsys, "check", str(db_path))
        assert code == 0, out
        assert "FAIL" not in out
        for step in (
            "database file",
            "schema version",
            "open read-only, check pragmas",
            "open read-write, check pragmas",
            "read-only connection refuses a write",
            "write site, recording, channel, transfer",
            "read back",
        ):
            assert f"PASS  {step}" in out


def test_check_missing_file(tmp_path, capsys):
    path = tmp_path / "missing.db"
    code, out = run(capsys, "check", str(path))
    assert code == 1
    assert "FAIL  database file: not found" in out
    assert not path.exists()


def test_check_refuses_a_database_of_another_app(tmp_path, capsys):
    path = tmp_path / "other.db"
    raw = sqlite3.connect(path, autocommit=True)
    raw.execute("CREATE TABLE t (x)")
    raw.close()
    code, out = run(capsys, "check", str(path))
    assert code == 1
    assert "FAIL  schema version: not_iqdm" in out


def test_write_on_an_idle_database(db_path, capsys):
    code, out = run(capsys, "write", str(db_path))
    assert code == 0
    assert "1 attempts" in out


@pytest.mark.parametrize("seconds", ["0", "-1", "601", "x"])
def test_hold_rejects_bad_seconds(db_path, seconds):
    with pytest.raises(SystemExit) as exc_info:
        db_check.main(["hold", str(db_path), "--seconds", seconds])
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Locking between two processes
# ---------------------------------------------------------------------------


def lock_then_write(db_path: Path, hold_s: float) -> tuple[subprocess.CompletedProcess, float, str]:
    """Start `hold` in one process, wait for the lock, then run `write` in another.

    Returns the write result, the write's elapsed time and the hold output.
    """
    holder = subprocess.Popen(
        [sys.executable, str(TOOL), "hold", str(db_path), "--seconds", str(hold_s)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert holder.stdout is not None
        lines = []
        while True:
            line = holder.stdout.readline()
            assert line, "hold exited before taking the lock: " + "".join(lines)
            lines.append(line)
            if "lock taken" in line:
                break
        t0 = time.perf_counter()
        writer = subprocess.run(
            [sys.executable, str(TOOL), "write", str(db_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        elapsed = time.perf_counter() - t0
        rest, _ = holder.communicate(timeout=60)
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait()
    assert holder.returncode == 0, "".join(lines) + rest
    return writer, elapsed, "".join(lines) + rest


def test_write_waits_for_a_short_lock(db_path):
    writer, elapsed, _ = lock_then_write(db_path, 3)
    assert writer.returncode == 0, writer.stdout
    assert "1 attempts" in writer.stdout  # the 5 s busy timeout covers a 3 s lock
    assert elapsed > 1.5


@pytest.mark.slow
def test_write_retries_through_a_longer_lock(db_path):
    writer, elapsed, _ = lock_then_write(db_path, 8)
    assert writer.returncode == 0, writer.stdout
    assert "database locked; retrying in 1 s" in writer.stdout
    assert "2 attempts" in writer.stdout
    assert elapsed > 6


@pytest.mark.slow
def test_write_gives_up_on_a_long_lock(db_path):
    writer, elapsed, _ = lock_then_write(db_path, 25)
    assert writer.returncode == 1
    assert "FAIL  write: database busy after" in writer.stdout
    assert "3 attempts" in writer.stdout
    assert 15 < elapsed < 25
