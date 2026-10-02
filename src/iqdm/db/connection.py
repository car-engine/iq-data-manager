"""Connections to the shared catalogue database (SPEC section 3, "DB access rules").

- Every connection sets foreign_keys and busy_timeout and uses the rollback journal.
- Connections are opened for one operation and closed straight after (open_db).
- Writes go through write_transaction: BEGIN IMMEDIATE, retry on a locked database,
  then DatabaseBusyError.
- Connections run in autocommit mode, so transactions are always explicit.
"""

import sqlite3
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from urllib.parse import quote

from iqdm.db.version import SchemaStatus, schema_status

BUSY_TIMEOUT_MS = 5000
RETRY_DELAYS_S: tuple[float, ...] = (1.0, 2.0)  # pauses between attempts (SPEC D7)


class DatabaseError(Exception):
    """Base class for database errors shown to the user."""


class DatabaseBusyError(DatabaseError):
    """The database stayed locked by another user through every retry."""


class SchemaVersionError(DatabaseError):
    """The database file's schema version does not allow this kind of access."""

    def __init__(self, status: SchemaStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


def schema_sql() -> str:
    """The bundled schema.sql text."""
    return resources.files("iqdm.db").joinpath("schema.sql").read_text(encoding="utf-8")


def verify_schema_in_memory() -> int:
    """Build schema.sql in an in-memory database and return its user_version.

    The --smoke-test of a frozen build uses this to show that the bundled sqlite3
    module and schema.sql work together. It touches no file.
    """
    conn = sqlite3.connect(":memory:", autocommit=True)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(f"BEGIN;\n{schema_sql()}\nCOMMIT;")
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def sqlite_uri(path: Path | str, mode: str) -> str:
    """SQLite `file:` URI for a path. mode is 'ro', 'rw' or 'rwc'.

    Drive paths become file:///C:/..., UNC paths file:////server/share/...
    (Path.as_uri() gives file://server/share/..., which SQLite rejects).
    """
    if mode not in ("ro", "rw", "rwc"):
        raise ValueError(f"mode must be 'ro', 'rw' or 'rwc', got {mode!r}")
    posix = Path(path).absolute().as_posix()
    prefix = "file://" if posix.startswith("/") else "file:///"
    return f"{prefix}{quote(posix, safe='/:')}?mode={mode}"


def _is_lock_error(exc: sqlite3.OperationalError) -> bool:
    name = getattr(exc, "sqlite_errorname", "") or ""
    return name.startswith(("SQLITE_BUSY", "SQLITE_LOCKED"))


def open_unchecked(path: Path | str, *, readonly: bool = False) -> sqlite3.Connection:
    """Open an existing database with the standard pragmas and no schema-version check.

    Only migrations use this directly. Everything else uses connect() or open_db().
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"database file not found: {p}")
    conn = sqlite3.connect(
        sqlite_uri(p, "ro" if readonly else "rw"),
        uri=True,
        autocommit=True,
        timeout=BUSY_TIMEOUT_MS / 1000,
    )
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {int(BUSY_TIMEOUT_MS)}")
        if not readonly:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if mode.lower() == "wal":  # never WAL on an SMB share
                mode = conn.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
            if mode.lower() != "delete":
                raise DatabaseError(f"unexpected journal mode {mode!r} for {p}")
    except BaseException:
        conn.close()
        raise
    return conn


def connect(path: Path | str, *, readonly: bool = False) -> sqlite3.Connection:
    """Open a database whose schema version allows this access (SPEC D6).

    Writes need the current version. Reads also accept a newer version.
    """
    conn = open_unchecked(path, readonly=readonly)
    try:
        status = schema_status(conn)
        allowed = {SchemaStatus.CURRENT} | ({SchemaStatus.TOO_NEW} if readonly else set())
        if status not in allowed:
            raise SchemaVersionError(status, _version_message(status, Path(path)))
    except BaseException:
        conn.close()
        raise
    return conn


def _version_message(status: SchemaStatus, path: Path) -> str:
    match status:
        case SchemaStatus.NEEDS_UPGRADE:
            return f"The database {path} uses an older schema. Upgrade it before use."
        case SchemaStatus.TOO_NEW:
            return f"The database {path} was written by a newer version of this app."
        case _:
            return f"{path} is not an IQ Data Manager database."


def database_status(path: Path | str) -> SchemaStatus:
    """Schema status of a database file, for the GUI to show at startup."""
    conn = open_unchecked(path, readonly=True)
    try:
        return schema_status(conn)
    finally:
        conn.close()


@contextmanager
def open_db(path: Path | str, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    """Connection that is always closed on exit. Use readonly=True for queries."""
    conn = connect(path, readonly=readonly)
    try:
        yield conn
    finally:
        conn.close()


def create_database(path: Path | str) -> None:
    """Create a new database from schema.sql. Refuses a path that already exists.

    The schema runs in one transaction. If it fails, an empty file may remain at
    `path`; the error message names it so the user can remove it.
    """
    p = Path(path)
    if p.exists():
        raise FileExistsError(f"refusing to create a database over an existing file: {p}")
    conn = sqlite3.connect(sqlite_uri(p, "rwc"), uri=True, autocommit=True)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(f"BEGIN IMMEDIATE;\n{schema_sql()}\nCOMMIT;")
    except sqlite3.Error as exc:
        raise DatabaseError(
            f"creating the schema failed; an empty file may remain at {p}: {exc}"
        ) from exc
    finally:
        conn.close()


def write_transaction[T](
    path: Path | str,
    fn: Callable[[sqlite3.Connection], T],
    *,
    delays: Sequence[float] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run fn(conn) in one write transaction and return its result.

    BEGIN IMMEDIATE takes the write lock before fn runs. On a locked or busy
    database the whole attempt is rolled back and retried after each pause in
    `delays` (default RETRY_DELAYS_S). fn may therefore run more than once, so it
    must only do database work. Any other error rolls back and is raised at once.
    """
    pauses = RETRY_DELAYS_S if delays is None else tuple(delays)
    attempts = len(pauses) + 1
    for attempt in range(attempts):
        try:
            with open_db(path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    result = fn(conn)
                    conn.execute("COMMIT")
                except BaseException:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise
                return result
        except sqlite3.OperationalError as exc:
            if not _is_lock_error(exc):
                raise
            if attempt == attempts - 1:
                raise DatabaseBusyError(
                    f"The database is in use by someone else. Tried {attempts} times; "
                    "try again in a minute."
                ) from exc
            sleep(pauses[attempt])
    raise AssertionError("unreachable")  # pragma: no cover
