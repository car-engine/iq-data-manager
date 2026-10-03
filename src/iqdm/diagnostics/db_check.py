"""Check a catalogue database at a given path: create, open, write and locking.

Open item O21 in docs/STATUS.md: before Milestone 3, the user tests a scratch database
on the NAS. The same commands also run against a local path. The tool uses the app's
own database code in iqdm.db, so it tests the code the app will run.

The code moved here from tools/db_check.py, which stays as a wrapper (D57).

Commands, in the packaged app or from the repository:
    IQDataManager-check.exe db-check create PATH            new, empty database from schema.sql
    IQDataManager-check.exe db-check check PATH             open, write and read back
    IQDataManager-check.exe db-check hold PATH --seconds N  keep the write lock for N seconds
    IQDataManager-check.exe db-check write PATH             one write through the retry logic
    python tools/db_check.py create PATH                    (and the same for the others)

Locking test: run `hold` on one PC (or in one terminal), then `write` on another
within N seconds. The write waits and succeeds once the lock is released. If the lock
is held for longer than about 18 s, the write fails with the "database is busy" error
(DECISIONS.md D7).

Use a scratch database only, never the real catalogue. `check` and `write` leave their
test rows in the database. `check`, `hold` and `write` refuse a database that holds any
recording other than the tool's own test rows (D57). The tool never deletes anything.

Exit codes: 0 every step passed, 1 a step failed, 2 usage error.
"""

import argparse
import getpass
import socket
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from iqdm.db import repository
from iqdm.db.connection import (
    BUSY_TIMEOUT_MS,
    Connection,
    DatabaseBusyError,
    connection_settings,
    create_database,
    database_status,
    open_db,
    write_transaction,
)
from iqdm.db.version import SchemaStatus
from iqdm.models import Channel, Operation, Recording, TransferEntry
from iqdm.timeutil import utc_now_iso

MAX_HOLD_S = 600.0
EXPECTED_SETTINGS = {"journal_mode": "delete", "foreign_keys": 1, "busy_timeout": BUSY_TIMEOUT_MS}
TEST_ROW_NOTE = "test row written by tools/db_check.py"  # unchanged, to match earlier rows


class Report:
    """Prints one line per step and remembers whether any step failed."""

    def __init__(self) -> None:
        self.failed = False

    def ok(self, step: str, detail: str = "") -> None:
        print(f"PASS  {step}" + (f": {detail}" if detail else ""), flush=True)

    def fail(self, step: str, detail: str) -> None:
        self.failed = True
        print(f"FAIL  {step}: {detail}", flush=True)

    def info(self, text: str) -> None:
        print(f"      {text}", flush=True)

    def run[T](self, step: str, fn: Callable[[], T]) -> tuple[bool, T | None]:
        """Run fn, print PASS with its time or FAIL with the error. Returns (ok, result)."""
        t0 = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:  # report every failure and carry on
            self.fail(step, f"{type(exc).__name__}: {exc}")
            return False, None
        self.ok(step, f"{time.perf_counter() - t0:.3f} s")
        return True, result

    @property
    def exit_code(self) -> int:
        return 1 if self.failed else 0


def _tag() -> str:
    """Unique text for this run: UTC time, PC name and a random suffix."""
    return f"{utc_now_iso()} {socket.gethostname()} {uuid.uuid4().hex[:8]}"


def scratch_only(path: Path, report: Report) -> bool:
    """True when the database holds no recording other than this tool's test rows.

    A database the app cannot open is left to the command, which reports the error.
    """
    try:
        with open_db(path, readonly=True) as conn:
            others = repository.count_recordings_except(conn, TEST_ROW_NOTE)
    except Exception:  # the command itself reports why the file cannot be used
        return True
    if others:
        report.fail(
            "scratch database",
            f"the database holds {others:,} recordings that this tool did not write. "
            "Run the check on a new scratch database (create PATH), never on the real "
            "catalogue.",
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_create(path: Path, report: Report) -> None:
    ok, _ = report.run("create database", lambda: create_database(path))
    if not ok:
        return
    status = database_status(path)
    if status is SchemaStatus.CURRENT:
        report.ok("schema version", "current")
    else:
        report.fail("schema version", str(status))


def _check_settings(path: Path, readonly: bool) -> None:
    with open_db(path, readonly=readonly) as conn:
        settings = connection_settings(conn)
    expected = dict(EXPECTED_SETTINGS)
    if readonly:
        del expected["journal_mode"]  # a read-only connection does not change the mode
        settings.pop("journal_mode")
    if settings != expected:
        raise AssertionError(f"got {settings}, expected {expected}")


def _refuse_readonly_write(path: Path) -> None:
    with open_db(path, readonly=True) as conn:
        try:
            repository.add_site(conn, f"db-check read-only {_tag()}")
        except Exception as exc:
            if "readonly" in str(exc).lower():
                return
            raise
    raise AssertionError("a read-only connection accepted a write")


def _write_test_rows(path: Path, tag: str) -> int:
    """Add a site, a one-channel recording and a transfer_log row. Returns the recording id."""
    user = getpass.getuser()
    now = time.time()

    def write(conn: Connection) -> int:
        site = repository.add_site(conn, f"db-check {tag}")
        if site.id is None:
            raise AssertionError("add_site returned no id")
        rec = Recording(
            logged_by=user,
            site_id=site.id,
            storage_root="db-check",
            rel_path=tag,
            channels=[
                Channel(
                    channel_index=0,
                    fc_hz=1e9,
                    fs_hz=1e6,
                    start_unix=now,
                    end_unix=now + 1,
                    n_files=1,
                    total_bytes=4_000_000,
                )
            ],
            remarks=TEST_ROW_NOTE,
        )
        rec_id = repository.insert_recording(conn, rec)
        repository.insert_transfer(
            conn,
            TransferEntry(
                recording_id=rec_id,
                operation=Operation.CHECK,
                source=str(path),
                started_at=utc_now_iso(),
                performed_by=user,
                notes=TEST_ROW_NOTE,
            ),
        )
        return rec_id

    return write_transaction(path, write)


def _read_back(path: Path, rec_id: int, tag: str) -> None:
    with open_db(path, readonly=True) as conn:
        rec = repository.get_recording(conn, rec_id)
        site = repository.get_site(conn, rec.site_id)
        transfers = repository.list_transfers(conn, rec_id)
    if site.name != f"db-check {tag}" or rec.rel_path != tag:
        raise AssertionError(f"read back site {site.name!r}, rel_path {rec.rel_path!r}")
    if len(rec.channels) != 1 or len(transfers) != 1:
        raise AssertionError(f"read back {len(rec.channels)} channels, {len(transfers)} transfers")


def cmd_check(path: Path, report: Report) -> None:
    if not path.is_file():
        report.fail("database file", f"not found: {path}")
        return
    report.ok("database file", f"{path.stat().st_size} bytes")
    ok, status = report.run("schema version", lambda: database_status(path))
    if not ok:
        return
    if status is not SchemaStatus.CURRENT:
        report.fail("schema version", str(status))
        return
    if not scratch_only(path, report):
        return
    report.run("open read-only, check pragmas", lambda: _check_settings(path, readonly=True))
    report.run("open read-write, check pragmas", lambda: _check_settings(path, readonly=False))
    report.run("read-only connection refuses a write", lambda: _refuse_readonly_write(path))
    tag = _tag()
    ok, rec_id = report.run(
        "write site, recording, channel, transfer", lambda: _write_test_rows(path, tag)
    )
    if ok and rec_id is not None:
        report.run("read back", lambda: _read_back(path, rec_id, tag))


def cmd_hold(path: Path, seconds: float, report: Report) -> None:
    if not scratch_only(path, report):
        return

    def hold(_conn: Connection) -> None:
        report.info(f"lock taken at {utc_now_iso()}, holding for {seconds:g} s")
        time.sleep(seconds)

    t0 = time.perf_counter()
    try:
        write_transaction(path, hold)
    except Exception as exc:
        report.fail("hold write lock", f"{type(exc).__name__}: {exc}")
        return
    report.ok(
        "hold write lock", f"released at {utc_now_iso()} after {time.perf_counter() - t0:.1f} s"
    )


def cmd_write(path: Path, report: Report) -> None:
    if not scratch_only(path, report):
        return
    pauses: list[float] = []

    def counting_sleep(s: float) -> None:
        pauses.append(s)
        report.info(f"database locked; retrying in {s:g} s")
        time.sleep(s)

    tag = _tag()
    t0 = time.perf_counter()
    try:
        write_transaction(
            path,
            lambda conn: repository.add_site(conn, f"db-check write {tag}"),
            sleep=counting_sleep,
        )
    except DatabaseBusyError as exc:
        report.fail(
            "write",
            f"database busy after {time.perf_counter() - t0:.1f} s and {len(pauses) + 1} "
            f"attempts: {exc}",
        )
        return
    except Exception as exc:
        report.fail("write", f"{type(exc).__name__}: {exc}")
        return
    report.ok("write", f"{time.perf_counter() - t0:.1f} s, {len(pauses) + 1} attempts")


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _seconds(text: str) -> float:
    value = float(text)
    if not 0 < value <= MAX_HOLD_S:
        raise argparse.ArgumentTypeError(f"must be more than 0 and at most {MAX_HOLD_S:g}")
    return value


def _build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog or "db_check.py",
        description="Check a scratch catalogue database: create, open, write and locking.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_text in [
        ("create", "create a new, empty database (refuses an existing file)"),
        ("check", "open, write test rows and read them back"),
        ("hold", "keep the write lock for --seconds"),
        ("write", "make one write through the app's retry logic"),
    ]:
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("path", type=Path, help="database file")
        if name == "hold":
            cmd.add_argument("--seconds", type=_seconds, default=10.0, help="default 10")
    return p


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    """Command-line entry point. Returns the exit code."""
    args = _build_parser(prog).parse_args(argv)
    report = Report()
    print(f"db_check {args.command} {args.path} on {socket.gethostname()} at {utc_now_iso()}")
    match args.command:
        case "create":
            cmd_create(args.path, report)
        case "check":
            cmd_check(args.path, report)
        case "hold":
            cmd_hold(args.path, args.seconds, report)
        case "write":
            cmd_write(args.path, report)
    print("RESULT " + ("FAIL" if report.failed else "PASS"), flush=True)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
