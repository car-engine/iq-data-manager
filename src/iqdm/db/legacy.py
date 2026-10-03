"""Read the legacy catalogue table, and write the legacy import (DECISIONS.md D66).

The legacy file is opened read-only, so the import cannot change it. The import
writes into a new database made by connection.create_database(), in one transaction,
through the repository. The rules that turn legacy rows into recordings live in
iqdm.legacy, which has no SQL.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from iqdm.db import repository
from iqdm.db.connection import DatabaseError, sqlite_uri, write_transaction
from iqdm.location import join_location
from iqdm.models import Recording

LEGACY_COLUMNS = (
    "date",
    "date_unix",
    "site",
    "band",
    "fc_hz",
    "fs_hz",
    "duration_s",
    "data_dir",
    "remarks",
)


class LegacyFormatError(DatabaseError):
    """The legacy file has no table with the expected columns."""


@dataclass(frozen=True, kw_only=True)
class LegacyRow:
    """One legacy row, with its values as SQLite returned them. row is the rowid."""

    row: int
    date: object
    date_unix: object
    site: object
    band: object
    fc_hz: object
    fs_hz: object
    duration_s: object
    data_dir: object
    remarks: object


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _choose_table(conn: sqlite3.Connection, table: str | None) -> str:
    names = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite\\_%'"
            " ESCAPE '\\' ORDER BY name"
        )
    ]
    if table is not None:
        if table not in names:
            raise LegacyFormatError(
                f"no table named {table!r}; the file holds: {', '.join(names) or 'no tables'}"
            )
        return table
    if len(names) != 1:
        raise LegacyFormatError(
            f"the file holds {len(names)} tables ({', '.join(names) or 'none'}); "
            "name the legacy table with --table"
        )
    return names[0]


def read_legacy_rows(path: Path | str, table: str | None = None) -> tuple[str, list[LegacyRow]]:
    """The legacy table's name and its rows in rowid order. Opens the file read-only.

    `table` None takes the only table in the file. Raises LegacyFormatError when the
    table is missing or lacks a column of LEGACY_COLUMNS, and FileNotFoundError when
    the file does not exist.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"legacy database not found: {p}")
    conn = sqlite3.connect(sqlite_uri(p, "ro"), uri=True, autocommit=True)
    try:
        name = _choose_table(conn, table)
        present = {r[1].lower() for r in conn.execute(f"PRAGMA table_info({_quoted(name)})")}
        missing = [c for c in LEGACY_COLUMNS if c not in present]
        if missing:
            raise LegacyFormatError(f"table {name!r} lacks the columns: {', '.join(missing)}")
        columns = ", ".join(LEGACY_COLUMNS)
        rows = conn.execute(
            f"SELECT rowid, {columns} FROM {_quoted(name)} ORDER BY rowid"  # noqa: S608
        ).fetchall()
    except sqlite3.Error as exc:
        raise LegacyFormatError(f"cannot read the legacy database {p}: {exc}") from exc
    finally:
        conn.close()
    return name, [
        LegacyRow(row=r[0], **dict(zip(LEGACY_COLUMNS, r[1:], strict=True))) for r in rows
    ]


def write_import(
    path: Path | str,
    sites: Sequence[str],
    recordings: Sequence[tuple[str, Recording]],
    *,
    performed_by: str,
    at: str,
) -> list[int]:
    """Write the sites and recordings into a new database in one transaction.

    Each recording comes with its site name, which must be one of `sites` ignoring
    letter case; its site_id is replaced. Each recording also gets the in-place row
    of DECISIONS.md D2 with the time `at`. Returns the new recording ids in order.
    """

    def work(conn: sqlite3.Connection) -> list[int]:
        site_ids = {name.casefold(): repository.add_site(conn, name).id for name in sites}
        ids = []
        for site_name, rec in recordings:
            site_id = site_ids[site_name.casefold()]
            if site_id is None:
                raise DatabaseError(f"site {site_name!r} was written without an id")
            recording_id = repository.insert_recording(conn, replace(rec, site_id=site_id))
            repository.insert_in_place_check(
                conn,
                recording_id,
                source=join_location(rec.storage_root, rec.rel_path),
                performed_by=performed_by,
                at=at,
            )
            ids.append(recording_id)
        return ids

    return write_transaction(path, work)
