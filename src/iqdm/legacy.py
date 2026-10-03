"""Import the legacy catalogue into a new database (DECISIONS.md D66, SPEC section 10).

The legacy file has one table, with one row per channel of a capture. This module
groups the rows into recordings, checks every value and writes a report of the rows
it cannot map. It guesses nothing: a group with any doubtful row is left out and
listed. iqdm.db.legacy reads the legacy file read-only and writes the new database;
this module has no SQL and no Qt.

Commands, in the packaged app or from the repository:
    IQDataManager-check.exe migrate-legacy LEGACY_DB NEW_DB --nas-root UNC [options]
    python tools/migrate_legacy.py LEGACY_DB NEW_DB --nas-root UNC [options]

Run it on a copy of the legacy database. NEW_DB must not exist. A real run writes the
report next to it as NEW_DB.report.txt; --dry-run only prints it.

Exit codes: 0 the import was written (or the dry run finished), 1 refused or failed,
2 usage error.
"""

import argparse
import math
import ntpath
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath

from iqdm.config import is_unc_path, nas_root_error
from iqdm.db.connection import DatabaseError, create_database
from iqdm.db.legacy import LegacyFormatError, LegacyRow, read_legacy_rows, write_import
from iqdm.location import LocationError, join_location, split_location
from iqdm.models import (
    ArchiveState,
    Channel,
    Endianness,
    IqLayout,
    Recording,
    SampleType,
)
from iqdm.timeutil import utc_now_iso

LOGGED_BY = "legacy-import"
LEGACY_ZONE = timezone(timedelta(hours=8))  # the legacy `date` text is at UTC+8
DATE_TOLERANCE_S = 1.0  # a larger gap between `date` and `date_unix` gives a warning
REMARKS_SEPARATOR = " | "
REPORT_SUFFIX = ".report.txt"
_CHANNEL_RE = re.compile(r"^(0|[1-9]\d*)$")  # a canonical decimal folder name (D11)
_DRIVE_RE = re.compile(r"^[A-Za-z]:$")
_SLASH_FORMATS = ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d")


@dataclass(frozen=True)
class Problem:
    """A line of the report: the legacy rows (rowids) it concerns and what is wrong."""

    rows: tuple[int, ...]
    text: str

    @property
    def line(self) -> str:
        label = "row" if len(self.rows) == 1 else "rows"
        return f"{label} {', '.join(str(r) for r in self.rows)}: {self.text}"


@dataclass(kw_only=True)
class ImportPlan:
    """What the import writes, and what it leaves out.

    Each recording comes with its site name. Its site_id is 0 until the import writes
    the sites. site_spellings maps each kept site name to the other spellings that
    were merged into it.
    """

    rows_read: int
    sites: list[str] = field(default_factory=list)
    recordings: list[tuple[str, Recording]] = field(default_factory=list)
    rejected: list[Problem] = field(default_factory=list)
    warnings: list[Problem] = field(default_factory=list)
    site_spellings: dict[str, list[str]] = field(default_factory=dict)

    @property
    def channel_count(self) -> int:
        return sum(len(rec.channels) for _, rec in self.recordings)

    @property
    def rows_rejected(self) -> int:
        return sum(len(p.rows) for p in self.rejected)


@dataclass(kw_only=True)
class _MappedRow:
    """A legacy row whose folder could be split. errors lists its wrong values."""

    row: LegacyRow
    storage_root: str
    rel_path: str
    channel_index: int
    sub_path: str
    errors: list[str]
    channel: Channel | None
    site: str
    remarks: str | None

    @property
    def folder(self) -> str:
        return join_location(self.storage_root, self.rel_path)


# =========================================================================
# Values
# =========================================================================


def _number(value: object) -> float | None:
    """A finite int or float as float, else None. Text is not converted."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _text(value: object) -> str | None:
    """Stripped text, or None for NULL or empty text. Numbers become their text."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def legacy_date_unix(value: object) -> float | None:
    """Unix seconds of a legacy `date` text read at UTC+8, or None if it cannot be read.

    Accepts ISO 8601 forms such as '2026-09-18 11:00:00' and '2026-09-18T11:00:00',
    and the same with slashes. A text with its own offset keeps that offset.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        for fmt in _SLASH_FORMATS:
            try:
                moment = datetime.strptime(text, fmt)  # noqa: DTZ007  (zone set below)
                break
            except ValueError:
                continue
        else:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=LEGACY_ZONE)
    return moment.timestamp()


def split_data_dir(data_dir: str) -> tuple[str, int, str]:
    """(recording folder, channel_index, sub_path) of a legacy data_dir (D66).

    A last folder named by a canonical decimal number is a channel folder (D11).
    Any other folder is the recording folder itself, with channel 0.
    """
    path = PureWindowsPath(ntpath.normpath(data_dir.strip()))
    if len(path.parts) >= 2 and _CHANNEL_RE.match(path.name):
        return str(path.parent), int(path.name), path.name
    return str(path), 0, ""


def parse_drive_map(items: Sequence[str]) -> dict[str, str]:
    """{'Z:': UNC} from --drive values such as 'Z:=\\\\server\\share'. Raises ValueError."""
    drives: dict[str, str] = {}
    for item in items:
        drive, sep, unc = item.partition("=")
        drive, unc = drive.strip(), unc.strip()
        if not sep or not _DRIVE_RE.match(drive) or not is_unc_path(unc):
            raise ValueError(f"--drive {item}: use the form Z:=\\\\server\\share")
        drives[drive.upper()] = unc
    return drives


def _value_errors(row: LegacyRow) -> list[str]:
    errors = []
    if _text(row.site) is None:
        errors.append("site is empty")
    if _number(row.date_unix) is None:
        errors.append(f"date_unix {row.date_unix!r} is not a number")
    duration = _number(row.duration_s)
    if duration is None or duration <= 0:
        errors.append(f"duration_s {row.duration_s!r} is not a number above 0")
    if _number(row.fc_hz) is None:
        errors.append(f"fc_hz {row.fc_hz!r} is not a number")
    fs = _number(row.fs_hz)
    if fs is None or fs <= 0:
        errors.append(f"fs_hz {row.fs_hz!r} is not a number above 0")
    return errors


def _map_row(
    row: LegacyRow, nas_roots: Sequence[str], drives: Mapping[str, str]
) -> _MappedRow | Problem:
    """The row with its folder split by D14, or the reason its folder cannot be used."""
    data_dir = row.data_dir if isinstance(row.data_dir, str) else ""
    if not data_dir.strip():
        return Problem((row.row,), "data_dir is empty")
    folder, index, sub_path = split_data_dir(data_dir)
    try:
        location = split_location(folder, nas_roots, drives.get)
    except LocationError as exc:
        return Problem((row.row,), f"{data_dir}: {exc}")
    if location.archive_state is not ArchiveState.ARCHIVED:
        return Problem((row.row,), f"{data_dir}: not under any NAS root given with --nas-root")
    errors = _value_errors(row)
    start, duration = _number(row.date_unix), _number(row.duration_s)
    fc, fs = _number(row.fc_hz), _number(row.fs_hz)
    channel = None
    if not errors and start is not None and duration is not None and fc is not None and fs:
        channel = Channel(
            channel_index=index,
            sub_path=sub_path,
            band=_text(row.band),
            fc_hz=fc,
            fs_hz=fs,
            start_unix=start,
            end_unix=start + duration,
        )
    return _MappedRow(
        row=row,
        storage_root=location.storage_root,
        rel_path=location.rel_path,
        channel_index=index,
        sub_path=sub_path,
        errors=errors,
        channel=channel,
        site=_text(row.site) or "",
        remarks=_text(row.remarks),
    )


def _date_warning(row: LegacyRow) -> Problem | None:
    """A warning when `date` cannot be read or is more than 1 s from `date_unix`."""
    date_unix = _number(row.date_unix)
    if date_unix is None:  # such a row never reaches a recording
        return None
    from_text = legacy_date_unix(row.date)
    if from_text is None:
        return Problem((row.row,), f"date {row.date!r} cannot be read; date_unix is used")
    gap = from_text - date_unix
    if abs(gap) > DATE_TOLERANCE_S:
        return Problem(
            (row.row,),
            f"date {row.date!r} (read at UTC+8) is {gap:+.0f} s from date_unix "
            f"{date_unix:.0f}; date_unix is used",
        )
    return None


# =========================================================================
# Grouping
# =========================================================================


def _group_problem(members: list[_MappedRow]) -> str | None:
    """Why a group of rows with one recording folder cannot become a recording."""
    bad = [f"row {m.row.row}: {'; '.join(m.errors)}" for m in members if m.errors]
    if bad:
        return "; ".join(bad)
    if len({m.sub_path == "" for m in members}) > 1:
        return "the rows mix channel folders with the recording folder itself"
    indices = [m.channel_index for m in members]
    repeated = sorted({i for i in indices if indices.count(i) > 1})
    if repeated:
        return f"channel {', '.join(str(i) for i in repeated)} appears in more than one row"
    sites = list(dict.fromkeys(m.site for m in members))
    if len({s.casefold() for s in sites}) > 1:
        return f"the rows name different sites: {', '.join(sites)}"
    return None


def build_plan(
    rows: Sequence[LegacyRow],
    nas_roots: Sequence[str],
    drives: Mapping[str, str] | None = None,
    *,
    now: str,
) -> ImportPlan:
    """Group legacy rows into recordings by D66. `now` becomes archived_at."""
    plan = ImportPlan(rows_read=len(rows))
    groups: dict[tuple[str, str], list[_MappedRow]] = {}
    for row in rows:
        mapped = _map_row(row, nas_roots, drives or {})
        if isinstance(mapped, Problem):
            plan.rejected.append(mapped)
            continue
        key = (mapped.storage_root.casefold(), mapped.rel_path.casefold())
        groups.setdefault(key, []).append(mapped)

    site_names: dict[str, str] = {}  # casefolded name -> the first spelling
    for members in groups.values():
        first = members[0]
        problem = _group_problem(members)
        if problem is not None:
            plan.rejected.append(
                Problem(tuple(m.row.row for m in members), f"{first.folder}: {problem}")
            )
            continue
        site = site_names.setdefault(first.site.casefold(), first.site)
        if first.site != site:
            spellings = plan.site_spellings.setdefault(site, [])
            if first.site not in spellings:
                spellings.append(first.site)
        remarks = list(dict.fromkeys(m.remarks for m in members if m.remarks))
        if len(remarks) > 1:
            plan.warnings.append(
                Problem(tuple(m.row.row for m in members), f"{first.folder}: remarks joined")
            )
        for m in members:
            warning = _date_warning(m.row)
            if warning is not None:
                plan.warnings.append(warning)
        channels = sorted((m.channel for m in members if m.channel), key=lambda c: c.channel_index)
        recording = Recording(
            logged_by=LOGGED_BY,
            site_id=0,
            storage_root=first.storage_root,
            rel_path=first.rel_path,
            channels=channels,
            file_duration_s=1.0,
            dtype=SampleType.INT16,
            iq_layout=IqLayout.INTERLEAVED_IQ,
            endianness=Endianness.LITTLE,
            header_bytes=0,
            archive_state=ArchiveState.ARCHIVED,
            archived_at=now,
            remarks=REMARKS_SEPARATOR.join(remarks) or None,
        )
        plan.recordings.append((site, recording))
    plan.sites = list(site_names.values())
    plan.rejected.sort(key=lambda p: p.rows)
    plan.warnings.sort(key=lambda p: p.rows)
    return plan


# =========================================================================
# Report
# =========================================================================


def report_text(plan: ImportPlan, *, legacy: Path, new: Path, table: str, now: str) -> str:
    """The report of an import, as printed and as written to NEW_DB.report.txt."""
    lines = [
        f"Legacy import at {now}",
        f"Legacy database: {legacy} (table {table})",
        f"New database:    {new}",
        "",
        f"Rows read:         {plan.rows_read}",
        f"Recordings:        {len(plan.recordings)} ({plan.channel_count} channels)",
        f"Sites:             {len(plan.sites)}",
        f"Rows not imported: {plan.rows_rejected}",
        f"Warnings:          {len(plan.warnings)}",
    ]
    if plan.rejected:
        lines += ["", "Rows not imported:"] + [f"  {p.line}" for p in plan.rejected]
    if plan.warnings:
        lines += ["", "Warnings (imported):"] + [f"  {p.line}" for p in plan.warnings]
    if plan.site_spellings:
        lines += ["", "Site spellings merged:"]
        lines += [
            f"  {kept} (also written {', '.join(others)})"
            for kept, others in plan.site_spellings.items()
        ]
    return "\n".join(lines)


# =========================================================================
# Command line
# =========================================================================


def _build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog or "migrate_legacy.py",
        description=(
            "Import the legacy catalogue into a new database. The legacy file is opened "
            "read-only. Run this on a copy of it."
        ),
    )
    p.add_argument("legacy", type=Path, help="copy of the legacy database file")
    p.add_argument("new", type=Path, help="new database file; must not exist")
    p.add_argument(
        "--nas-root",
        action="append",
        required=True,
        metavar="UNC",
        help="a NAS root, as \\\\server\\share\\folder; give one --nas-root for each",
    )
    p.add_argument(
        "--drive",
        action="append",
        default=[],
        metavar="Z:=UNC",
        help="a drive letter used in data_dir and the UNC path it stands for",
    )
    p.add_argument("--table", help="name of the legacy table, if the file holds more than one")
    p.add_argument("--dry-run", action="store_true", help="print the report and write nothing")
    return p


def _same_file(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def _fail(prog: str, text: str) -> int:
    print(f"{prog}: {text}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    """Command-line entry point. Returns the exit code."""
    parser = _build_parser(prog)
    args = parser.parse_args(argv)
    name = parser.prog
    problems = [e for e in (nas_root_error(r) for r in args.nas_root) if e]
    try:
        drives = parse_drive_map(args.drive)
    except ValueError as exc:
        problems.append(str(exc))
    if problems:
        parser.error("; ".join(problems))

    legacy: Path = args.legacy
    new: Path = args.new
    report_path = new.with_name(new.name + REPORT_SUFFIX)
    if _same_file(legacy, new):
        return _fail(name, "the new database cannot be the legacy file")
    if new.exists():
        return _fail(name, f"refusing to write over an existing file: {new}")
    if not args.dry_run and report_path.exists():
        return _fail(name, f"refusing to write over an existing file: {report_path}")
    try:
        table, rows = read_legacy_rows(legacy, args.table)
    except (FileNotFoundError, LegacyFormatError) as exc:
        return _fail(name, str(exc))

    now = utc_now_iso()
    plan = build_plan(rows, [r.strip() for r in args.nas_root], drives, now=now)
    text = report_text(plan, legacy=legacy, new=new, table=table, now=now)
    print(text)
    print()
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0
    if not plan.recordings:
        return _fail(name, "no recording can be imported; nothing written")
    try:
        create_database(new)
        ids = write_import(new, plan.sites, plan.recordings, performed_by=LOGGED_BY, at=now)
    except (OSError, DatabaseError, ValueError) as exc:
        return _fail(
            name,
            f"the import failed: {exc}\nThe file {new} may remain with an empty schema. "
            "Remove it before you run the import again.",
        )
    print(f"Wrote {len(ids)} recordings to {new}.")
    try:
        with report_path.open("x", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError as exc:
        return _fail(name, f"the database is complete, but the report was not written: {exc}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
