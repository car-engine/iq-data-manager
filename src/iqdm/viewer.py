"""Viewer tab logic without Qt: filters, table text, details, gap lines and loading.

SPEC section 5. The GUI collects a FilterInput, calls parse_filter(), then loads the
list with load_list() in a worker. Times are shown and entered at the configured
offset from UTC (D24, D43). Coverage below the configured threshold is marked (D39).
A recording logged in place on the NAS is marked as not verified (D2, D44).
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath

from iqdm.db import repository
from iqdm.db.connection import DatabaseError, SchemaVersionError, open_db
from iqdm.db.version import SchemaStatus, schema_status
from iqdm.entry import format_mhz, format_size, missing_text, parse_mhz
from iqdm.location import join_location
from iqdm.models import (
    IN_PLACE_NOTE,
    ArchiveState,
    Channel,
    Operation,
    Param,
    Recording,
    RecordingFilter,
    RecordingSummary,
    Site,
    TransferEntry,
    Verification,
)
from iqdm.scan.scanner import ScanResult
from iqdm.timeutil import display_time, iso_to_unix

TIMES = "\N{MULTIPLICATION SIGN}"
DOT = " \N{MIDDLE DOT} "
UNKNOWN = "unknown"
DATE_FORMAT = "%Y-%m-%d"
GAPS_LISTED = 10  # gaps named per channel in the gap lines; the rest are counted
DAY_S = 86400.0


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class FilterInput:
    """The filter fields as the user entered them. Empty text leaves a filter out."""

    start_from: str = ""
    start_to: str = ""
    site_id: int | None = None
    band: str = ""
    fc_min: str = ""
    fc_max: str = ""
    archive_state: ArchiveState | None = None
    rf_chain_text: str = ""
    remarks_text: str = ""


@dataclass(frozen=True)
class FilterResult:
    """A filter ready for the repository, or the messages that say what is wrong."""

    flt: RecordingFilter | None
    errors: tuple[str, ...] = ()


def parse_date(text: str, offset_hours: float) -> float:
    """'2026-09-30' as Unix seconds of 00:00 that day at the display offset (D43).

    Raises ValueError for any other form.
    """
    day = datetime.strptime(text.strip(), DATE_FORMAT)  # noqa: DTZ007  (zone set below)
    zone = timezone(timedelta(hours=offset_hours))
    return day.replace(tzinfo=zone).timestamp()


def parse_filter(form: FilterInput, offset_hours: float) -> FilterResult:
    """Check the filter fields. "To" includes the whole day, so its bound is the next 00:00."""
    errors: list[str] = []
    start_from = _date_bound(form.start_from, "Start date from", offset_hours, errors)
    start_to = _date_bound(form.start_to, "Start date to", offset_hours, errors)
    if start_from is not None and start_to is not None and start_to < start_from:
        errors.append("Start date to is before Start date from.")
    fc_min = _mhz_bound(form.fc_min, "Centre frequency min", errors)
    fc_max = _mhz_bound(form.fc_max, "Centre frequency max", errors)
    if fc_min is not None and fc_max is not None and fc_max < fc_min:
        errors.append("Centre frequency max is below min.")
    if errors:
        return FilterResult(None, tuple(errors))
    return FilterResult(
        RecordingFilter(
            start_from_unix=start_from,
            start_before_unix=None if start_to is None else start_to + DAY_S,
            site_id=form.site_id,
            band=form.band.strip() or None,
            fc_min_hz=fc_min,
            fc_max_hz=fc_max,
            archive_state=form.archive_state,
            rf_chain_text=form.rf_chain_text.strip() or None,
            remarks_text=form.remarks_text.strip() or None,
        )
    )


def _date_bound(text: str, label: str, offset_hours: float, errors: list[str]) -> float | None:
    if not text.strip():
        return None
    try:
        return parse_date(text, offset_hours)
    except ValueError:
        errors.append(f"{label}: use the form YYYY-MM-DD, for example 2026-09-30.")
        return None


def _mhz_bound(text: str, label: str, errors: list[str]) -> float | None:
    if not text.strip():
        return None
    try:
        return parse_mhz(text)
    except ValueError:
        errors.append(f"{label}: enter a positive number in MHz, for example 145.8.")
        return None


# ---------------------------------------------------------------------------
# Table text
# ---------------------------------------------------------------------------


def span_text(seconds: float) -> str:
    """'2 h 05 m', '45 m 00 s', '12 s'. Fractions of a second are dropped."""
    total = max(0, math.floor(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} m"
    if minutes:
        return f"{minutes} m {secs:02d} s"
    return f"{secs} s"


def fc_summary(fc_hz: Sequence[float]) -> str:
    """Centre frequencies in MHz: '433.92 (times) 2' when all are equal, else '145.8 · 435'."""
    if not fc_hz:
        return ""
    if len(fc_hz) > 1 and len(set(fc_hz)) == 1:
        return f"{format_mhz(fc_hz[0])} {TIMES} {len(fc_hz)}"
    return DOT.join(format_mhz(f) for f in fc_hz)


def coverage_percent(coverage: float | None) -> float | None:
    """Coverage as a percentage at one decimal place, as shown."""
    return None if coverage is None else round(100 * coverage, 1)


def coverage_text(coverage: float | None) -> str:
    """'99.7%', or 'unknown' when the file count is not in the database."""
    percent = coverage_percent(coverage)
    return UNKNOWN if percent is None else f"{percent:.1f}%"


def coverage_is_low(coverage: float | None, threshold_percent: float) -> bool:
    """True when the shown coverage is below the threshold (D39). Unknown is not low."""
    percent = coverage_percent(coverage)
    return percent is not None and percent < threshold_percent


def size_text(n_bytes: int | None) -> str:
    return UNKNOWN if n_bytes is None else format_size(n_bytes)


def state_text(state: ArchiveState, unverified: bool) -> str:
    """'local', 'archived', or 'archived, not verified' (D2)."""
    if state is ArchiveState.ARCHIVED and unverified:
        return "archived, not verified"
    return str(state)


def is_unverified(rec: Recording, transfers: Iterable[TransferEntry]) -> bool:
    """True for an archived recording with the logged-in-place row (D2, D44).

    The same rule as RecordingSummary.unverified in repository.list_recordings().
    """
    return rec.archive_state is ArchiveState.ARCHIVED and any(
        t.operation is Operation.CHECK
        and t.verification is Verification.SKIPPED
        and t.notes == IN_PLACE_NOTE
        for t in transfers
    )


NOT_VERIFIED_NOTE = (
    "Logged where it lies on the NAS. Its files were never compared with the "
    "recording laptop's copy."
)


# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ParamRow:
    """One RF chain line in the details panel. `scope` is 'Recording' or 'Ch 1'."""

    scope: str
    param: str
    value: str  # with its unit
    note: str = ""


def _value_with_unit(p: Param) -> str:
    unit = (p.unit or "").strip()
    return f"{p.value} {unit}" if unit else p.value


def effective_params(rec: Recording, channel_index: int | None) -> list[ParamRow]:
    """The RF chain that applies to one channel, or the Recording rows when None (D28).

    A channel row replaces the Recording row of the same name for that channel. The
    replaced value is named in the channel row's note.
    """
    recording_rows = [p for p in rec.params if p.channel_index is None]
    if channel_index is None:
        return [
            ParamRow(scope="Recording", param=p.param, value=_value_with_unit(p))
            for p in recording_rows
        ]
    own = [p for p in rec.params if p.channel_index == channel_index]
    own_names = {p.param.casefold() for p in own}
    by_name = {p.param.casefold(): p for p in recording_rows}
    rows = [
        ParamRow(scope="Recording", param=p.param, value=_value_with_unit(p))
        for p in recording_rows
        if p.param.casefold() not in own_names
    ]
    for p in own:
        replaced = by_name.get(p.param.casefold())
        note = ""
        if replaced is not None and _value_with_unit(replaced) != _value_with_unit(p):
            note = f"replaces the Recording value {_value_with_unit(replaced)}"
        rows.append(
            ParamRow(
                scope=f"Ch {channel_index}", param=p.param, value=_value_with_unit(p), note=note
            )
        )
    return rows


def recording_path(rec: Recording) -> str:
    return join_location(rec.storage_root, rec.rel_path)


def channel_path(rec: Recording, channel: Channel) -> str:
    base = recording_path(rec)
    return str(PureWindowsPath(base, channel.sub_path)) if channel.sub_path else base


def format_text(rec: Recording) -> str:
    """'int16 · interleaved_iq · little-endian · no header · 1 s files'."""
    header = "no header" if rec.header_bytes == 0 else f"{rec.header_bytes:,}-byte header"
    return DOT.join(
        [
            str(rec.dtype),
            str(rec.iq_layout),
            f"{rec.endianness}-endian",
            header,
            f"{rec.file_duration_s:g} s files",
        ]
    )


@dataclass(frozen=True, kw_only=True)
class TransferRow:
    """One line of transfer history."""

    when: str
    operation: str
    scope: str
    result: str
    by: str
    notes: str = ""


_OPERATIONS = {Operation.MOVE: "Move", Operation.COPY: "Copy", Operation.CHECK: "Check"}
_RESULTS = {
    Verification.PASS: "verified",
    Verification.FAIL: "verification failed",
    Verification.SKIPPED: "not verified",
}


def iso_display(text: str, offset_hours: float) -> str:
    """Stored ISO 8601 UTC text as 'YYYY-MM-DD HH:MM' at the display offset (D24).

    Text in another form is returned unchanged.
    """
    try:
        return display_time(iso_to_unix(text), offset_hours)[:16]
    except ValueError:
        return text


def transfer_rows(entries: Iterable[TransferEntry], offset_hours: float) -> list[TransferRow]:
    rows = []
    for e in entries:
        if e.range_start_unix is None and e.range_end_unix is None:
            scope = "whole recording"
        else:
            start = (
                "start"
                if e.range_start_unix is None
                else display_time(e.range_start_unix, offset_hours)
            )
            end = (
                "end" if e.range_end_unix is None else display_time(e.range_end_unix, offset_hours)
            )
            scope = f"{start} to {end}"
        if e.channels is not None:
            scope += f", channel {', '.join(str(i) for i in e.channels)}"
        parts = []
        if e.n_files is not None:
            parts.append(f"{e.n_files:,} files")
        if e.total_bytes is not None:
            parts.append(format_size(e.total_bytes))
        parts.append(_RESULTS[e.verification] if e.finished_at is not None else "not finished")
        rows.append(
            TransferRow(
                when=iso_display(e.started_at, offset_hours),
                operation=_OPERATIONS[e.operation],
                scope=scope,
                result=DOT.join(parts),
                by=e.performed_by,
                notes=e.notes or "",
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Gap scan
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class TimelineRow:
    """One channel on the coverage timeline. Gaps are (start_unix, missing_seconds)."""

    label: str
    start_unix: float
    end_unix: float
    gaps: tuple[tuple[float, float], ...] = ()


def timeline_rows(scan: ScanResult) -> list[TimelineRow]:
    """Channels with files, with their gaps from the scan (D12)."""
    rows = []
    for ch in scan.channels:
        if ch.start_unix is None or ch.end_unix is None:
            continue
        rows.append(
            TimelineRow(
                label=f"Ch {ch.channel_index}",
                start_unix=ch.start_unix,
                end_unix=ch.end_unix,
                gaps=tuple((g.start_unix, g.missing_seconds) for g in ch.gaps),
            )
        )
    return rows


def _seconds_text(seconds: float) -> str:
    return f"{seconds:g} s"


def gap_lines(scan: ScanResult, offset_hours: float) -> list[str]:
    """One line per channel, for example
    'Ch 1: 12 missing seconds in 3 gaps: 2026-09-18 03:12:04 (3 s), ...'.
    """
    lines = []
    for ch in scan.channels:
        label = f"Ch {ch.channel_index}"
        if not ch.files:
            lines.append(f"{label}: no data files.")
            continue
        if not ch.gaps:
            lines.append(f"{label}: no gaps.")
            continue
        missing = sum(g.missing_seconds for g in ch.gaps)
        count = len(ch.gaps)
        listed = ", ".join(
            f"{display_time(g.start_unix, offset_hours)} ({_seconds_text(g.missing_seconds)})"
            for g in ch.gaps[:GAPS_LISTED]
        )
        more = f", and {count - GAPS_LISTED} more" if count > GAPS_LISTED else ""
        gaps = "1 gap" if count == 1 else f"{count:,} gaps"
        lines.append(f"{label}: {missing_text(missing)} in {gaps}: {listed}{more}.")
    return lines


def scan_differences(rec: Recording, scan: ScanResult) -> list[str]:
    """Where the folder differs from the database entry. Empty when they agree."""
    stored = {c.channel_index: c for c in rec.channels}
    found = {c.channel_index: c for c in scan.channels}
    lines = []
    for index in sorted(stored.keys() - found.keys()):
        lines.append(f"Channel {index} is in the database but not in the folder.")
    for index in sorted(found.keys() - stored.keys()):
        lines.append(f"Channel {index} is in the folder but not in the database.")
    for index in sorted(stored.keys() & found.keys()):
        db, disk = stored[index], found[index]
        if db.n_files is not None and db.n_files != disk.n_files:
            lines.append(
                f"Channel {index}: the folder holds {disk.n_files:,} files, the database "
                f"lists {db.n_files:,}."
            )
        elif db.total_bytes is not None and db.total_bytes != disk.total_bytes:
            lines.append(
                f"Channel {index}: the files hold {format_size(disk.total_bytes)}, the "
                f"database lists {format_size(db.total_bytes)}."
            )
    return lines


def recording_folder(rec: Recording) -> Path:
    """The folder the gap scan reads."""
    return Path(recording_path(rec))


# ---------------------------------------------------------------------------
# Loading (read-only connections, run in a worker)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ListResult:
    summaries: list[RecordingSummary]
    newer_database: bool = False  # written by a newer app version: read-only (D6)


@dataclass(frozen=True, kw_only=True)
class ViewerChoices:
    sites: list[Site]
    bands: list[str]


@dataclass(frozen=True, kw_only=True)
class Details:
    recording: Recording
    site_name: str
    transfers: list[TransferEntry]


def load_list(db_path: Path | str, flt: RecordingFilter | None) -> ListResult:
    with open_db(db_path, readonly=True) as conn:
        newer = schema_status(conn) is SchemaStatus.TOO_NEW
        return ListResult(summaries=repository.list_recordings(conn, flt), newer_database=newer)


def load_choices(db_path: Path | str) -> ViewerChoices:
    with open_db(db_path, readonly=True) as conn:
        return ViewerChoices(sites=repository.list_sites(conn), bands=repository.list_bands(conn))


def load_details(db_path: Path | str, recording_id: int) -> Details:
    with open_db(db_path, readonly=True) as conn:
        rec = repository.get_recording(conn, recording_id)
        return Details(
            recording=rec,
            site_name=repository.get_site(conn, rec.site_id).name,
            transfers=repository.list_transfers(conn, recording_id),
        )


NEWER_DATABASE = (
    "This database comes from a newer version of IQ Data Manager. The Viewer can show it, "
    "but some details may be missing."
)


def error_text(exc: BaseException) -> str:
    """A plain message for a failed database read. The technical text goes in a tooltip."""
    if isinstance(exc, FileNotFoundError):
        return (
            "Database file not found. Check the path in the Settings tab and the network "
            "connection."
        )
    if isinstance(exc, SchemaVersionError):
        if exc.status is SchemaStatus.NEEDS_UPGRADE:
            return (
                "This database comes from an older version of IQ Data Manager. This version "
                "cannot open it."
            )
        return "This file is not an IQ Data Manager database. Check the path in the Settings tab."
    if isinstance(exc, repository.NotFoundError):
        return "This recording is no longer in the database. Click Refresh."
    if isinstance(exc, DatabaseError | OSError):
        return "Cannot read the database. Check the network connection and click Refresh."
    return "Cannot read the database. Click Refresh to try again."
