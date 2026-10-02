"""All queries and writes for sites, recordings, channels, params and the transfer log.

Every function takes an open connection. The caller decides the transaction:
writes run inside connection.write_transaction, queries on a read-only connection
from connection.open_db. All SQL uses parameters.

Rules from DECISIONS.md D7:
- date, start_unix and end_unix of a recording are derived from its channels.
- A Param names its channel by channel_index. This module maps it to channel_id.
- update_recording updates channels in place by channel_index. Removing a channel
  needs allow_channel_removal=True, because it also deletes that channel's params.
"""

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from iqdm.db.connection import DatabaseError
from iqdm.models import (
    IN_PLACE_NOTE,
    ArchiveState,
    Channel,
    Endianness,
    HashMode,
    IqLayout,
    Operation,
    Param,
    Recording,
    RecordingFilter,
    RecordingSummary,
    SampleType,
    Site,
    TransferEntry,
    Verification,
    envelope,
    recording_coverage,
)
from iqdm.timeutil import unix_to_iso


class RepositoryError(DatabaseError):
    """A write was refused because of the data it would create or remove."""


class NotFoundError(RepositoryError):
    pass


class DuplicateSiteError(RepositoryError):
    pass


class DuplicateLocationError(RepositoryError):
    """The folder (storage_root, rel_path) is already logged."""


class HasTransferHistoryError(RepositoryError):
    """The recording has transfer_log rows, so it cannot be deleted."""


class AlreadyArchivedError(RepositoryError):
    """A move finished for a recording that another move archived first."""


class ChannelRemovalError(RepositoryError):
    """An update would remove channels without allow_channel_removal=True."""


def _rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    return cur.execute(sql, params).fetchall()


def _one(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _is_unique_violation(exc: sqlite3.IntegrityError, columns: str) -> bool:
    return f"UNIQUE constraint failed: {columns}" in str(exc)


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------


def _site(row: sqlite3.Row) -> Site:
    return Site(id=row["id"], name=row["name"], created_at=row["created_at"])


def add_site(conn: sqlite3.Connection, name: str) -> Site:
    """Add a site. Names are unique ignoring case."""
    clean = name.strip()
    if not clean:
        raise ValueError("site name is empty")
    try:
        row = _one(
            conn,
            "INSERT INTO sites (name) VALUES (?) RETURNING id, name, created_at",
            (clean,),
        )
    except sqlite3.IntegrityError as exc:
        if _is_unique_violation(exc, "sites.name"):
            raise DuplicateSiteError(f"site {clean!r} already exists") from exc
        raise
    if row is None:
        raise RepositoryError(f"inserting site {clean!r} returned no row")
    return _site(row)


def list_sites(conn: sqlite3.Connection) -> list[Site]:
    rows = _rows(conn, "SELECT id, name, created_at FROM sites ORDER BY name COLLATE NOCASE")
    return [_site(r) for r in rows]


def get_site(conn: sqlite3.Connection, site_id: int) -> Site:
    row = _one(conn, "SELECT id, name, created_at FROM sites WHERE id = ?", (site_id,))
    if row is None:
        raise NotFoundError(f"no site with id {site_id}")
    return _site(row)


def find_site(conn: sqlite3.Connection, name: str) -> Site | None:
    """Site with this name, ignoring case, or None."""
    row = _one(conn, "SELECT id, name, created_at FROM sites WHERE name = ?", (name.strip(),))
    return None if row is None else _site(row)


# ---------------------------------------------------------------------------
# Recordings: writes
# ---------------------------------------------------------------------------


def _check_recording(rec: Recording) -> None:
    """Checks the schema cannot express. Raises ValueError before anything is written."""
    if not rec.channels:
        raise ValueError("a recording needs at least one channel")
    indices = [c.channel_index for c in rec.channels]
    if len(set(indices)) != len(indices):
        raise ValueError(f"duplicate channel indices: {sorted(indices)}")
    for p in rec.params:
        if p.channel_index is not None and p.channel_index not in indices:
            raise ValueError(f"param {p.param!r} refers to missing channel {p.channel_index}")


def _recording_values(rec: Recording) -> tuple[Any, ...]:
    start, end = envelope(rec.channels)
    return (
        rec.logged_by,
        unix_to_iso(start),
        start,
        end,
        rec.file_duration_s,
        rec.site_id,
        str(rec.dtype),
        str(rec.iq_layout),
        str(rec.endianness),
        rec.header_bytes,
        rec.storage_root,
        rec.rel_path,
        str(rec.archive_state),
        rec.archived_at,
        rec.recording_plan_ref,
        rec.remarks,
    )


def _location_error(rec: Recording, exc: sqlite3.IntegrityError) -> Exception:
    if _is_unique_violation(exc, "recordings.storage_root, recordings.rel_path"):
        return DuplicateLocationError(
            f"{rec.rel_path!r} under {rec.storage_root!r} is already logged"
        )
    return exc


def _channel_values(ch: Channel) -> tuple[Any, ...]:
    return (
        ch.sub_path,
        ch.band,
        ch.fc_hz,
        ch.fs_hz,
        ch.start_unix,
        ch.end_unix,
        ch.n_files,
        ch.total_bytes,
    )


def _insert_channel(conn: sqlite3.Connection, recording_id: int, ch: Channel) -> int:
    row = conn.execute(
        "INSERT INTO channels (recording_id, channel_index, sub_path, band, fc_hz, fs_hz,"
        " start_unix, end_unix, n_files, total_bytes)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (recording_id, ch.channel_index, *_channel_values(ch)),
    ).fetchone()
    return row[0]


def _insert_params(
    conn: sqlite3.Connection,
    recording_id: int,
    params: Iterable[Param],
    channel_ids: Mapping[int, int],
) -> None:
    conn.executemany(
        "INSERT INTO recording_params (recording_id, channel_id, param, value, unit)"
        " VALUES (?, ?, ?, ?, ?)",
        [
            (
                recording_id,
                None if p.channel_index is None else channel_ids[p.channel_index],
                p.param,
                p.value,
                p.unit,
            )
            for p in params
        ],
    )


def insert_recording(conn: sqlite3.Connection, rec: Recording) -> int:
    """Insert a recording with its channels and params. Returns the new id.

    rec.id, date, start_unix, end_unix, created_at and updated_at are ignored.
    """
    _check_recording(rec)
    try:
        row = conn.execute(
            "INSERT INTO recordings (logged_by, date, start_unix, end_unix, file_duration_s,"
            " site_id, dtype, iq_layout, endianness, header_bytes, storage_root, rel_path,"
            " archive_state, archived_at, recording_plan_ref, remarks)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
            _recording_values(rec),
        ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise _location_error(rec, exc) from exc
    recording_id = row[0]
    channel_ids = {c.channel_index: _insert_channel(conn, recording_id, c) for c in rec.channels}
    _insert_params(conn, recording_id, rec.params, channel_ids)
    return recording_id


def update_recording(
    conn: sqlite3.Connection, rec: Recording, *, allow_channel_removal: bool = False
) -> None:
    """Update a recording, its channels (in place by index) and its params (as a set)."""
    if rec.id is None:
        raise ValueError("update_recording needs rec.id")
    _check_recording(rec)
    existing = {
        r["channel_index"]: r["id"]
        for r in _rows(
            conn, "SELECT id, channel_index FROM channels WHERE recording_id = ?", (rec.id,)
        )
    }
    if not existing and _one(conn, "SELECT 1 FROM recordings WHERE id = ?", (rec.id,)) is None:
        raise NotFoundError(f"no recording with id {rec.id}")
    new_indices = {c.channel_index for c in rec.channels}
    removed = sorted(set(existing) - new_indices)
    if removed and not allow_channel_removal:
        raise ChannelRemovalError(
            f"update would remove channels {removed} and their parameters"
        )

    try:
        cur = conn.execute(
            "UPDATE recordings SET logged_by = ?, date = ?, start_unix = ?, end_unix = ?,"
            " file_duration_s = ?, site_id = ?, dtype = ?, iq_layout = ?, endianness = ?,"
            " header_bytes = ?, storage_root = ?, rel_path = ?, archive_state = ?,"
            " archived_at = ?, recording_plan_ref = ?, remarks = ? WHERE id = ?",
            (*_recording_values(rec), rec.id),
        )
    except sqlite3.IntegrityError as exc:
        raise _location_error(rec, exc) from exc
    if cur.rowcount == 0:
        raise NotFoundError(f"no recording with id {rec.id}")

    conn.executemany("DELETE FROM channels WHERE id = ?", [(existing[i],) for i in removed])
    channel_ids: dict[int, int] = {}
    for ch in rec.channels:
        if ch.channel_index in existing:
            channel_id = existing[ch.channel_index]
            conn.execute(
                "UPDATE channels SET sub_path = ?, band = ?, fc_hz = ?, fs_hz = ?,"
                " start_unix = ?, end_unix = ?, n_files = ?, total_bytes = ? WHERE id = ?",
                (*_channel_values(ch), channel_id),
            )
        else:
            channel_id = _insert_channel(conn, rec.id, ch)
        channel_ids[ch.channel_index] = channel_id

    conn.execute("DELETE FROM recording_params WHERE recording_id = ?", (rec.id,))
    _insert_params(conn, rec.id, rec.params, channel_ids)


def update_archive_location(
    conn: sqlite3.Connection,
    recording_id: int,
    *,
    storage_root: str,
    rel_path: str,
    archived_at: str,
) -> None:
    """Point a recording at its verified NAS copy and mark it archived.

    Raises DuplicateLocationError if another recording uses that location.
    """
    try:
        cur = conn.execute(
            "UPDATE recordings SET storage_root = ?, rel_path = ?, archive_state = 'archived',"
            " archived_at = ? WHERE id = ?",
            (storage_root, rel_path, archived_at, recording_id),
        )
    except sqlite3.IntegrityError as exc:
        if _is_unique_violation(exc, "recordings.storage_root, recordings.rel_path"):
            raise DuplicateLocationError(
                f"{rel_path!r} under {storage_root!r} is already logged"
            ) from exc
        raise
    if cur.rowcount == 0:
        raise NotFoundError(f"no recording with id {recording_id}")


def update_channel_counts(
    conn: sqlite3.Connection, recording_id: int, counts: Mapping[int, tuple[int, int]]
) -> None:
    """Set (n_files, total_bytes) per channel_index, e.g. after "Check archive"."""
    for index, (n_files, total_bytes) in counts.items():
        cur = conn.execute(
            "UPDATE channels SET n_files = ?, total_bytes = ?"
            " WHERE recording_id = ? AND channel_index = ?",
            (n_files, total_bytes, recording_id, index),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"recording {recording_id} has no channel {index}")


def delete_recording(conn: sqlite3.Connection, recording_id: int) -> None:
    """Delete a catalogue entry (not its files). Refused if it has transfer history."""
    if _one(conn, "SELECT 1 FROM transfer_log WHERE recording_id = ?", (recording_id,)):
        raise HasTransferHistoryError(
            f"recording {recording_id} has transfer history and cannot be deleted"
        )
    cur = conn.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
    if cur.rowcount == 0:
        raise NotFoundError(f"no recording with id {recording_id}")


# ---------------------------------------------------------------------------
# Recordings: reads
# ---------------------------------------------------------------------------


def _channel(row: sqlite3.Row) -> Channel:
    return Channel(
        id=row["id"],
        channel_index=row["channel_index"],
        sub_path=row["sub_path"],
        band=row["band"],
        fc_hz=row["fc_hz"],
        fs_hz=row["fs_hz"],
        start_unix=row["start_unix"],
        end_unix=row["end_unix"],
        n_files=row["n_files"],
        total_bytes=row["total_bytes"],
    )


def get_recording(conn: sqlite3.Connection, recording_id: int) -> Recording:
    """A recording with its channels (by index) and params (in insertion order)."""
    row = _one(conn, "SELECT * FROM recordings WHERE id = ?", (recording_id,))
    if row is None:
        raise NotFoundError(f"no recording with id {recording_id}")
    channels = [
        _channel(r)
        for r in _rows(
            conn,
            "SELECT id, recording_id, channel_index, sub_path, band, fc_hz, fs_hz,"
            " start_unix, end_unix, n_files, total_bytes"
            " FROM channels WHERE recording_id = ? ORDER BY channel_index",
            (recording_id,),
        )
    ]
    params = [
        Param(
            id=r["id"],
            param=r["param"],
            value=r["value"],
            unit=r["unit"],
            channel_index=r["channel_index"],
        )
        for r in _rows(
            conn,
            "SELECT p.id, p.param, p.value, p.unit, c.channel_index"
            " FROM recording_params p LEFT JOIN channels c ON c.id = p.channel_id"
            " WHERE p.recording_id = ? ORDER BY p.id",
            (recording_id,),
        )
    ]
    return Recording(
        id=row["id"],
        logged_by=row["logged_by"],
        site_id=row["site_id"],
        storage_root=row["storage_root"],
        rel_path=row["rel_path"],
        channels=channels,
        params=params,
        file_duration_s=row["file_duration_s"],
        dtype=SampleType(row["dtype"]),
        iq_layout=IqLayout(row["iq_layout"]),
        endianness=Endianness(row["endianness"]),
        header_bytes=row["header_bytes"],
        archive_state=ArchiveState(row["archive_state"]),
        archived_at=row["archived_at"],
        recording_plan_ref=row["recording_plan_ref"],
        remarks=row["remarks"],
        date=row["date"],
        start_unix=row["start_unix"],
        end_unix=row["end_unix"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def find_recording_by_location(
    conn: sqlite3.Connection, storage_root: str, rel_path: str
) -> int | None:
    """Id of the recording logged at this folder, or None."""
    row = _one(
        conn,
        "SELECT id FROM recordings WHERE storage_root = ? AND rel_path = ?",
        (storage_root, rel_path),
    )
    return None if row is None else row["id"]


def like_pattern(text: str) -> str:
    """A LIKE pattern that matches `text` anywhere, with % and _ taken literally.

    Use it with ESCAPE '\\'.
    """
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filter_sql(flt: RecordingFilter | None) -> tuple[str, list[Any]]:
    """WHERE clause on recordings `r` for a Viewer filter, and its parameters."""
    if flt is None:
        return "1", []
    clauses: list[str] = []
    params: list[Any] = []
    if flt.start_from_unix is not None:
        clauses.append("r.start_unix >= ?")
        params.append(flt.start_from_unix)
    if flt.start_before_unix is not None:
        clauses.append("r.start_unix < ?")
        params.append(flt.start_before_unix)
    if flt.site_id is not None:
        clauses.append("r.site_id = ?")
        params.append(flt.site_id)
    if flt.archive_state is not None:
        clauses.append("r.archive_state = ?")
        params.append(str(flt.archive_state))
    channel_terms: list[str] = []  # band and fc range must match on one channel
    if flt.band:
        channel_terms.append("c.band = ? COLLATE NOCASE")
        params.append(flt.band)
    if flt.fc_min_hz is not None:
        channel_terms.append("c.fc_hz >= ?")
        params.append(flt.fc_min_hz)
    if flt.fc_max_hz is not None:
        channel_terms.append("c.fc_hz <= ?")
        params.append(flt.fc_max_hz)
    if channel_terms:  # S608: the terms are fixed text; values are parameters
        clauses.append(
            "EXISTS (SELECT 1 FROM channels c WHERE c.recording_id = r.id AND "  # noqa: S608
            + " AND ".join(channel_terms)
            + ")"
        )
    if flt.rf_chain_text:
        pattern = like_pattern(flt.rf_chain_text)
        clauses.append(
            "EXISTS (SELECT 1 FROM recording_params p WHERE p.recording_id = r.id AND"
            " (p.param LIKE ? ESCAPE '\\' OR p.value LIKE ? ESCAPE '\\'"
            " OR p.unit LIKE ? ESCAPE '\\'))"
        )
        params.extend([pattern, pattern, pattern])
    if flt.remarks_text:
        clauses.append("r.remarks LIKE ? ESCAPE '\\'")
        params.append(like_pattern(flt.remarks_text))
    return (" AND ".join(clauses) or "1"), params


def list_recordings(
    conn: sqlite3.Connection, flt: RecordingFilter | None = None
) -> list[RecordingSummary]:
    """Recordings that match the filter (all when None), newest first.

    The filter runs in SQL. Channels are read only for the matching recordings (O16).
    """
    # S608 below: `where` comes from _filter_sql(), fixed text only; values are parameters.
    where, params = _filter_sql(flt)
    recordings = _rows(
        conn,
        "SELECT r.id, r.date, r.start_unix, r.end_unix, r.file_duration_s,"  # noqa: S608
        " r.archive_state, r.logged_by, s.name AS site_name,"
        " (r.archive_state = 'archived' AND EXISTS (SELECT 1 FROM transfer_log t"
        "  WHERE t.recording_id = r.id AND t.operation = 'check'"
        "  AND t.verification = 'skipped' AND t.notes = ?)) AS unverified"
        " FROM recordings r JOIN sites s ON s.id = r.site_id"
        f" WHERE {where}"
        " ORDER BY r.start_unix DESC, r.id DESC",
        [IN_PLACE_NOTE, *params],
    )
    channels_by_recording: dict[int, list[Channel]] = {}
    for r in _rows(
        conn,
        "SELECT id, recording_id, channel_index, sub_path, band, fc_hz, fs_hz,"  # noqa: S608
        " start_unix, end_unix, n_files, total_bytes FROM channels"
        f" WHERE recording_id IN (SELECT r.id FROM recordings r WHERE {where})"
        " ORDER BY recording_id, channel_index",
        params,
    ):
        channels_by_recording.setdefault(r["recording_id"], []).append(_channel(r))

    summaries = []
    for r in recordings:
        chans = channels_by_recording.get(r["id"], [])
        sizes = [c.total_bytes for c in chans]
        summaries.append(
            RecordingSummary(
                id=r["id"],
                date=r["date"],
                start_unix=r["start_unix"],
                end_unix=r["end_unix"],
                site_name=r["site_name"],
                channel_count=len(chans),
                fc_hz=tuple(c.fc_hz for c in chans),
                total_bytes=(
                    None
                    if not sizes or None in sizes
                    else sum(s for s in sizes if s is not None)
                ),
                coverage=recording_coverage(chans, r["file_duration_s"]),
                archive_state=ArchiveState(r["archive_state"]),
                logged_by=r["logged_by"],
                unverified=bool(r["unverified"]),
            )
        )
    return summaries


def list_param_names(conn: sqlite3.Connection) -> list[str]:
    """Distinct parameter names for autocomplete, one spelling per name ignoring case."""
    rows = conn.execute(
        "SELECT MIN(param) FROM recording_params GROUP BY param ORDER BY 1 COLLATE NOCASE"
    ).fetchall()
    return [r[0] for r in rows]


def list_bands(conn: sqlite3.Connection) -> list[str]:
    """Distinct channel bands for the Log tab's dropdown, one spelling per band ignoring case.

    NULL and empty bands are left out (DECISIONS.md D19).
    """
    rows = conn.execute(
        "SELECT MIN(band) FROM channels WHERE band IS NOT NULL AND band <> ''"
        " GROUP BY band COLLATE NOCASE ORDER BY 1 COLLATE NOCASE"
    ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Transfer log
# ---------------------------------------------------------------------------


def encode_channels(indices: Iterable[int] | None) -> str | None:
    """Channel subset as stored in transfer_log.channels: None, or sorted '0,2'."""
    if indices is None:
        return None
    unique = sorted(set(indices))
    if not unique:
        raise ValueError("a channel subset cannot be empty; use None for all channels")
    if unique[0] < 0:
        raise ValueError(f"channel indices must be >= 0, got {unique}")
    return ",".join(str(i) for i in unique)


def decode_channels(text: str | None) -> tuple[int, ...] | None:
    return None if text is None else tuple(int(part) for part in text.split(","))


def insert_transfer(conn: sqlite3.Connection, entry: TransferEntry) -> int:
    """Add a transfer_log row. Returns its id.

    A delete row needs parent_id: a move of the same recording that passed
    verification. The schema refuses any other delete row (D52).
    """
    row = conn.execute(
        "INSERT INTO transfer_log (recording_id, operation, parent_id, source, destination,"
        " range_start_unix, range_end_unix, channels, hash_mode, started_at, finished_at,"
        " n_files, total_bytes, verification, performed_by, notes, manifest_path,"
        " manifest_sha256)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (
            entry.recording_id,
            str(entry.operation),
            entry.parent_id,
            entry.source,
            entry.destination,
            entry.range_start_unix,
            entry.range_end_unix,
            encode_channels(entry.channels),
            None if entry.hash_mode is None else str(entry.hash_mode),
            entry.started_at,
            entry.finished_at,
            entry.n_files,
            entry.total_bytes,
            str(entry.verification),
            entry.performed_by,
            entry.notes,
            entry.manifest_path,
            entry.manifest_sha256,
        ),
    ).fetchone()
    return row[0]


def finish_transfer(
    conn: sqlite3.Connection,
    transfer_id: int,
    *,
    finished_at: str,
    verification: Verification,
    n_files: int | None = None,
    total_bytes: int | None = None,
    notes: str | None = None,
    manifest_path: str | None = None,
    manifest_sha256: str | None = None,
) -> None:
    """Record the end of a transfer. Refused if the row is already finished.

    None leaves n_files, total_bytes, notes and the manifest fields as stored.
    """
    row = _one(conn, "SELECT finished_at FROM transfer_log WHERE id = ?", (transfer_id,))
    if row is None:
        raise NotFoundError(f"no transfer with id {transfer_id}")
    if row["finished_at"] is not None:
        raise RepositoryError(f"transfer {transfer_id} already finished at {row['finished_at']}")
    conn.execute(
        "UPDATE transfer_log SET finished_at = ?, verification = ?,"
        " n_files = COALESCE(?, n_files), total_bytes = COALESCE(?, total_bytes),"
        " notes = COALESCE(?, notes), manifest_path = COALESCE(?, manifest_path),"
        " manifest_sha256 = COALESCE(?, manifest_sha256) WHERE id = ?",
        (
            finished_at,
            str(verification),
            n_files,
            total_bytes,
            notes,
            manifest_path,
            manifest_sha256,
            transfer_id,
        ),
    )


def finish_move(
    conn: sqlite3.Connection,
    transfer_id: int,
    *,
    finished_at: str,
    n_files: int,
    total_bytes: int,
    manifest_path: str,
    manifest_sha256: str,
    storage_root: str,
    rel_path: str,
) -> None:
    """Finish a passed move and point its recording at the new copy (SPEC section 8).

    Both writes happen in the caller's transaction, so the log row and the archive
    state change together. archived_at is the finish time. Raises AlreadyArchivedError
    when the recording is no longer local, for example after a second move of the
    same recording finished first.
    """
    entry = get_transfer(conn, transfer_id)
    if entry.operation is not Operation.MOVE:
        raise RepositoryError(f"transfer {transfer_id} is a {entry.operation}, not a move")
    row = _one(conn, "SELECT archive_state FROM recordings WHERE id = ?", (entry.recording_id,))
    if row is None:
        raise NotFoundError(f"no recording with id {entry.recording_id}")
    if row["archive_state"] != str(ArchiveState.LOCAL):
        raise AlreadyArchivedError(f"recording {entry.recording_id} is already archived")
    finish_transfer(
        conn,
        transfer_id,
        finished_at=finished_at,
        verification=Verification.PASS,
        n_files=n_files,
        total_bytes=total_bytes,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
    )
    update_archive_location(
        conn,
        entry.recording_id,
        storage_root=storage_root,
        rel_path=rel_path,
        archived_at=finished_at,
    )


def _transfer(r: sqlite3.Row) -> TransferEntry:
    return TransferEntry(
        id=r["id"],
        recording_id=r["recording_id"],
        operation=Operation(r["operation"]),
        parent_id=r["parent_id"],
        source=r["source"],
        destination=r["destination"],
        range_start_unix=r["range_start_unix"],
        range_end_unix=r["range_end_unix"],
        channels=decode_channels(r["channels"]),
        hash_mode=None if r["hash_mode"] is None else HashMode(r["hash_mode"]),
        started_at=r["started_at"],
        finished_at=r["finished_at"],
        n_files=r["n_files"],
        total_bytes=r["total_bytes"],
        verification=Verification(r["verification"]),
        performed_by=r["performed_by"],
        notes=r["notes"],
        manifest_path=r["manifest_path"],
        manifest_sha256=r["manifest_sha256"],
    )


def get_transfer(conn: sqlite3.Connection, transfer_id: int) -> TransferEntry:
    row = _one(conn, "SELECT * FROM transfer_log WHERE id = ?", (transfer_id,))
    if row is None:
        raise NotFoundError(f"no transfer with id {transfer_id}")
    return _transfer(row)


def list_transfers(conn: sqlite3.Connection, recording_id: int) -> list[TransferEntry]:
    """Transfer history of one recording, oldest first."""
    return [
        _transfer(r)
        for r in _rows(
            conn,
            "SELECT * FROM transfer_log WHERE recording_id = ? ORDER BY started_at, id",
            (recording_id,),
        )
    ]
