"""Numbered schema migrations based on PRAGMA user_version (SPEC section 3 and D6).

The app never migrates on startup. upgrade() runs only from an explicit,
user-confirmed action. Its sequence:

1. Take the write lock (BEGIN IMMEDIATE) so no other writer can change the file.
2. Write a backup next to the database through SQLite's online backup API. An
   existing file is never overwritten.
3. Apply each migration in its own transaction. user_version and a
   foreign_key_check run inside that transaction, so a failed step rolls back and
   leaves the database at the last good version.
4. Run PRAGMA quick_check.

Until the first real database exists, schema.sql is edited in place (SPEC D4) and
MIGRATIONS stays empty.
"""

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from iqdm.db import version
from iqdm.db.connection import (
    DatabaseError,
    SchemaVersionError,
    open_unchecked,
    sqlite_uri,
)
from iqdm.db.version import SchemaStatus, schema_status


@dataclass(frozen=True)
class Migration:
    """Moves the schema from `from_version` to `from_version + 1`.

    Set disable_foreign_keys for steps that rebuild tables. The pragma cannot change
    inside a transaction, so upgrade() switches it off before BEGIN and checks
    foreign keys before COMMIT.
    """

    from_version: int
    description: str
    apply: Callable[[sqlite3.Connection], None]
    disable_foreign_keys: bool = False


MIGRATIONS: tuple[Migration, ...] = ()


class MigrationError(DatabaseError):
    """A migration step failed or the migration chain is incomplete."""


@dataclass(frozen=True)
class UpgradeResult:
    from_version: int
    to_version: int
    backup_path: Path | None  # None when the database was already current
    applied: tuple[str, ...]  # descriptions of the steps applied


def backup_path_for(db_path: Path, from_version: int, now: datetime) -> Path:
    """<stem>.v<N>-backup-<UTC stamp><suffix>, next to the database."""
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return db_path.with_name(f"{db_path.stem}.v{from_version}-backup-{stamp}{db_path.suffix}")


def backup_database(db_path: Path | str, from_version: int, now: datetime | None = None) -> Path:
    """Copy the database to a new backup file and verify the copy. Never overwrites."""
    source_path = Path(db_path)
    target = backup_path_for(source_path, from_version, now or datetime.now(UTC))
    with target.open("xb"):  # exclusive create: fails if the file exists
        pass
    src = open_unchecked(source_path, readonly=True)
    try:
        dst = sqlite3.connect(sqlite_uri(target, "rw"), uri=True, autocommit=True)
        try:
            src.backup(dst)
            copied_version = dst.execute("PRAGMA user_version").fetchone()[0]
            check = dst.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            dst.close()
    finally:
        src.close()
    if copied_version != from_version or check != "ok":
        raise MigrationError(
            f"backup {target} failed verification (version {copied_version}, check {check!r})"
        )
    return target


def _plan(current: int, target: int, migrations: Sequence[Migration]) -> list[Migration]:
    by_version = {m.from_version: m for m in migrations}
    steps = []
    for v in range(current, target):
        if v not in by_version:
            raise MigrationError(f"no migration from schema version {v} to {v + 1}")
        steps.append(by_version[v])
    return steps


def _apply_step(conn: sqlite3.Connection, step: Migration, *, begun: bool) -> None:
    """Run one migration in a transaction. `begun` means BEGIN IMMEDIATE already ran."""
    if step.disable_foreign_keys:
        if begun:
            raise MigrationError("cannot switch off foreign keys inside an open transaction")
        conn.execute("PRAGMA foreign_keys = OFF")
    try:
        if not begun:
            conn.execute("BEGIN IMMEDIATE")
        step.apply(conn)
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise MigrationError(f"foreign key check failed: {problems[:5]}")
        conn.execute(f"PRAGMA user_version = {int(step.from_version) + 1}")
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        if step.disable_foreign_keys:
            conn.execute("PRAGMA foreign_keys = ON")


def upgrade(
    db_path: Path | str,
    *,
    migrations: Sequence[Migration] | None = None,
    latest: int | None = None,
    now: datetime | None = None,
) -> UpgradeResult:
    """Back up the database, then migrate it to `latest` (default LATEST_VERSION)."""
    steps_available = MIGRATIONS if migrations is None else migrations
    target = version.LATEST_VERSION if latest is None else latest
    path = Path(db_path)

    conn = open_unchecked(path)
    try:
        status = schema_status(conn, target)
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        if status is SchemaStatus.CURRENT:
            return UpgradeResult(current, current, None, ())
        if status is not SchemaStatus.NEEDS_UPGRADE:
            raise SchemaVersionError(status, f"cannot upgrade {path}: status {status}")
        steps = _plan(current, target, steps_available)

        # Hold the write lock while the backup is taken, so the backup matches the
        # data the first step migrates. Readers are still allowed. A first step that
        # switches off foreign keys must start its own transaction after the pragma,
        # so in that case the backup is taken without the lock.
        first_needs_fk_off = steps[0].disable_foreign_keys
        if first_needs_fk_off:
            backup = backup_database(path, current, now)
        else:
            conn.execute("BEGIN IMMEDIATE")
            try:
                backup = backup_database(path, current, now)
            except BaseException:
                conn.execute("ROLLBACK")
                raise

        applied: list[str] = []
        for i, step in enumerate(steps):
            begun = i == 0 and not first_needs_fk_off
            try:
                _apply_step(conn, step, begun=begun)
            except Exception as exc:
                reached = conn.execute("PRAGMA user_version").fetchone()[0]
                raise MigrationError(
                    f"migration {step.from_version}->{step.from_version + 1} "
                    f"({step.description}) failed: {exc}. The database is at version "
                    f"{reached}. Backup: {backup}"
                ) from exc
            applied.append(step.description)

        check = conn.execute("PRAGMA quick_check").fetchone()[0]
        if check != "ok":
            raise MigrationError(f"quick_check after upgrade returned {check!r}. Backup: {backup}")
        return UpgradeResult(current, target, backup, tuple(applied))
    finally:
        conn.close()
