"""Archive / copy tab logic without Qt (SPEC section 8).

- Time input at the display offset, kept in sync with Unix seconds (D59).
- The form's values turned into a TransferRequest, and a stored transfer turned back
  into form values for Resume.
- The destination filled in for a copy to a PC (D60).
- The preview as lines for the checklist widget.
- The state of the laptop copy after an archive: check before delete, delete (D55).
- Check before delete straight after each archive, for the form and the queue (D97).
- The tab's pages, and the page the Viewer's button opens (D96).
- The fields of the Archive and Copy pages to fill in or correct (D101).
- The state of an unfinished copy or archive, and progress, speed and time left.
"""

import math
import ntpath
import re
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path, PureWindowsPath

from iqdm.db import repository
from iqdm.db.connection import open_db, write_transaction
from iqdm.entry import ChecklistItem, ItemState, format_size, missing_text
from iqdm.location import join_location
from iqdm.models import (
    ArchiveState,
    HashMode,
    Operation,
    Recording,
    TransferEntry,
    Verification,
)
from iqdm.timeutil import offset_label
from iqdm.transfer.copier import CopyProgress
from iqdm.transfer.delete import DeleteRefused, checked_before_delete
from iqdm.transfer.estimate import duration_text
from iqdm.transfer.operations import (
    CHECK_NEEDS_HASHES,
    Preview,
    TransferRequest,
    check_before_delete,
)
from iqdm.transfer.pathcheck import files_text
from iqdm.transfer.verify import VerifyProgress

FILES_LISTED = 200  # file names shown in the preview's file list; the rest are counted
SPEED_WINDOW_S = 10.0  # the speed is averaged over this many seconds
CHECK_AFTER_ARCHIVE_TEXT = (
    'After the archive, "Check before delete" reads the NAS copy again, past this PC\'s file '
    "cache. The estimated time does not include it."
)

# ---------------------------------------------------------------------------
# Time input (D59)
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2})(\.\d{1,6})?)?)?$"
)
TIME_HINT = "YYYY-MM-DD HH:MM:SS"


class FormError(ValueError):
    """The form cannot become a transfer. messages lists every problem."""

    def __init__(self, messages: Sequence[str]) -> None:
        self.messages = tuple(messages)
        super().__init__(" ".join(self.messages))


def parse_time_input(text: str, offset_hours: float) -> float:
    """'YYYY-MM-DD HH:MM:SS' at the display offset as Unix seconds.

    Seconds and the time of day may be left out; a fraction of a second is allowed.
    Raises ValueError with a message for the user.
    """
    m = _TIME_RE.match(text.strip())
    if m is None:
        raise ValueError(f"Write the time as {TIME_HINT}.")
    year, month, day, hour, minute, second, fraction = m.groups()
    zone = timezone(timedelta(hours=offset_hours))
    try:
        moment = datetime(
            int(year),
            int(month),
            int(day),
            int(hour or 0),
            int(minute or 0),
            int(second or 0),
            tzinfo=zone,
        )
    except ValueError:
        raise ValueError(f"{text.strip()} is not a valid date and time.") from None
    return moment.timestamp() + (float(fraction) if fraction else 0.0)


def format_time_input(t: float, offset_hours: float) -> str:
    """Unix seconds as 'YYYY-MM-DD HH:MM:SS' at the display offset, with a fraction of a
    second when there is one (up to 6 places)."""
    whole = math.floor(t)
    zone = timezone(timedelta(hours=offset_hours))
    text = datetime.fromtimestamp(whole, tz=zone).strftime("%Y-%m-%d %H:%M:%S")
    fraction = round(t - whole, 6)
    if fraction >= 1:  # rounding reached the next second
        return format_time_input(whole + 1, offset_hours)
    if fraction:
        text += f"{fraction:.6f}".rstrip("0")[1:]
    return text


def parse_unix_input(text: str) -> float:
    """Unix seconds as typed. Raises ValueError with a message for the user."""
    try:
        value = float(text.strip())
    except ValueError:
        raise ValueError("Unix time is a number of seconds, for example 1790733600.") from None
    if not math.isfinite(value) or value < 0:
        raise ValueError("Unix time is a number of seconds, for example 1790733600.")
    return value


def format_unix_input(t: float) -> str:
    """Unix seconds without a needless '.0'."""
    return f"{t:.6f}".rstrip("0").rstrip(".")


def time_label(name: str, offset_hours: float) -> str:
    """'From (UTC+8)'."""
    return f"{name} ({offset_label(offset_hours)})"


# ---------------------------------------------------------------------------
# Form values and requests
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class FormInput:
    """The Archive / copy form as the user filled it in.

    start_unix and end_unix come from the time fields; None means a field is empty
    or wrong, and time_errors says why. channels holds the ticked channels.
    """

    operation: Operation  # COPY or ARCHIVE
    recording: Recording | None
    whole: bool
    start_unix: float | None = None
    end_unix: float | None = None
    time_errors: tuple[str, ...] = ()
    channels: tuple[int, ...] = ()
    destination: str = ""
    hash_mode: HashMode = HashMode.SAMPLE


def request_from_form(form: FormInput) -> TransferRequest:
    """The request the form describes. Raises FormError that lists the problems.

    An archive always takes the whole recording with all channels (D50).
    """
    errors: list[str] = []
    rec = form.recording
    if rec is None or rec.id is None:
        errors.append("Choose a recording.")
    if not form.destination.strip():
        errors.append("Choose a destination folder.")
    channels: tuple[int, ...] | None = None
    start = end = None
    if form.operation is Operation.COPY and rec is not None:
        if not form.channels:
            errors.append("Select at least one channel.")
        all_channels = {c.channel_index for c in rec.channels}
        if set(form.channels) != all_channels:
            channels = tuple(sorted(form.channels))
        if not form.whole:
            errors += form.time_errors
            if not form.time_errors:
                start, end = form.start_unix, form.end_unix
                if start is None or end is None:
                    errors.append("Enter the start and the end of the range.")
                elif end <= start:
                    errors.append("The end of the range must be after its start.")
    if errors or rec is None or rec.id is None:
        raise FormError(errors)
    return TransferRequest(
        recording_id=rec.id,
        operation=form.operation,
        destination=form.destination.strip(),
        hash_mode=form.hash_mode,
        channels=channels,
        start_unix=start,
        end_unix=end,
    )


def form_from_transfer(entry: TransferEntry, rec: Recording) -> FormInput:
    """Form values that run a stored copy or archive again (Resume)."""
    indices = tuple(c.channel_index for c in rec.channels)
    whole = entry.range_start_unix is None and entry.range_end_unix is None
    return FormInput(
        operation=entry.operation,
        recording=rec,
        whole=whole,
        start_unix=entry.range_start_unix,
        end_unix=entry.range_end_unix,
        channels=indices if entry.channels is None else entry.channels,
        destination=entry.destination or "",
        hash_mode=entry.hash_mode or HashMode.SAMPLE,
    )


def default_copy_destination(copy_root: str | None, rel_path: str) -> str:
    """The local copy folder and the recording's relative path (D60). '' without a
    local copy folder."""
    if not copy_root or not copy_root.strip():
        return ""
    return ntpath.normpath(ntpath.join(copy_root.strip(), rel_path))


def archive_destination(nas_folder: str, rel_path: str) -> str:
    """The NAS folder for archives and the recording's relative path (D81, D96). '' without
    a NAS folder."""
    return default_copy_destination(nas_folder, rel_path)


# ---------------------------------------------------------------------------
# Fields to fill in or correct (D101)
# ---------------------------------------------------------------------------


class FormField(StrEnum):
    FOLDER = "folder"  # the NAS folder for archives, or the folder for copies
    DESTINATION = "destination"
    CHANNELS = "channels"
    FROM = "from"
    TO = "to"


def destination_errors(preview: Preview) -> list[str]:
    """The preview's errors that concern the destination folder: the destination checks
    (D51, D75), and another recording logged at an archive's destination (D50)."""
    errors = list(preview.check.errors)
    errors += [
        e
        for e in preview.errors
        if e not in errors and e.endswith("is already logged at the destination folder.")
    ]
    return errors


def form_marks(
    form: FormInput,
    *,
    folder: str,
    time_errors: Mapping[str, str],
    preview: Preview | None = None,
) -> dict[FormField, ChecklistItem]:
    """Each field of the Archive or Copy page that is empty but needed (TODO), or wrong
    (ERROR), with the reason (D101, after D95).

    `folder` is the page's folder field. An empty destination marks that folder when it
    is empty too, because the folder fills in the destination; else the destination
    itself. `time_errors` holds the time fields' own errors by "from" and "to". A
    preview, made for this form, adds its destination errors. Errors that belong to no
    field, such as "The recording is already archived.", give no mark.
    """
    marks: dict[FormField, ChecklistItem] = {}
    rec = form.recording
    if rec is None:
        return marks
    archive = form.operation is Operation.ARCHIVE
    if not form.destination.strip():
        if not folder.strip():
            what = '"NAS folder for archives"' if archive else '"Folder for copies"'
            marks[FormField.FOLDER] = ChecklistItem(ItemState.TODO, f"Choose the {what}.")
        else:
            marks[FormField.DESTINATION] = ChecklistItem(
                ItemState.TODO, "Choose a destination folder."
            )
    elif preview is not None:
        errors = destination_errors(preview)
        if errors:
            marks[FormField.DESTINATION] = ChecklistItem(ItemState.ERROR, " ".join(errors))
    if archive:
        return marks
    if not form.channels:
        marks[FormField.CHANNELS] = ChecklistItem(ItemState.TODO, "Select at least one channel.")
    if form.whole:
        return marks
    for key, field, value, name in (
        ("from", FormField.FROM, form.start_unix, "start"),
        ("to", FormField.TO, form.end_unix, "end"),
    ):
        if time_errors.get(key):
            marks[field] = ChecklistItem(ItemState.ERROR, time_errors[key])
        elif value is None:
            marks[field] = ChecklistItem(ItemState.TODO, f"Enter the {name} of the range.")
    start, end = form.start_unix, form.end_unix
    if start is not None and end is not None and end <= start:
        marks[FormField.TO] = ChecklistItem(
            ItemState.ERROR, "The end of the range must be after its start."
        )
    return marks


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class PreviewSummary:
    """The figures at the top of the preview, and its lines."""

    files: str
    size: str
    missing: str
    time: str
    lines: tuple[ChecklistItem, ...]


def _hash_text(preview: Preview) -> str:
    mode = preview.request.hash_mode
    n = preview.selection.n_files
    if mode is HashMode.NONE:
        return "The check after the copy compares file sizes only."
    return (
        f"The check after the copy compares every file's size and hashes "
        f"{preview.hashed_files:,} of {n:,} files."
    )


def _in_place_text(preview: Preview) -> str | None:
    existing = preview.check.existing
    if not existing:
        return None
    sizes = {f.rel_path: f.size for f in preview.selection.files}
    in_place = sum(sizes[p] for p in existing)
    to_copy = preview.selection.n_files - len(existing)
    after = (
        "Their sizes are compared with the rest after the copy."
        if preview.request.hash_mode is HashMode.NONE
        else "They are hashed with the rest after the copy."
    )
    return (
        f"{files_text(len(existing))} already in the destination with the right size "
        f"({format_size(in_place)}). They are not copied again. {after} "
        f"{files_text(to_copy)} to copy ({format_size(preview.check.bytes_to_copy)})."
    )


def missing_lines(preview: Preview) -> list[str]:
    """'Channel 1: 6 missing seconds', one per channel with missing seconds."""
    return [
        f"Channel {c.channel_index}: {missing_text(c.missing_seconds)}"
        for c in preview.selection.channels
        if c.missing_seconds
    ]


def preview_summary(preview: Preview, speed_mb_s: float) -> PreviewSummary:
    """The preview's figures and lines. Errors first, then warnings and information."""
    lines = [ChecklistItem(ItemState.ERROR, e) for e in preview.errors]
    lines += [ChecklistItem(ItemState.INFO, w) for w in preview.warnings]
    if preview.check.ok:
        lines.append(
            ChecklistItem(
                ItemState.OK,
                "Destination checked: not a drive or share root, outside the source, no "
                "file would be replaced, enough free space.",
            )
        )
    lines += [ChecklistItem(ItemState.INFO, n) for n in preview.check.notes]
    in_place = _in_place_text(preview)
    if in_place is not None:
        lines.append(ChecklistItem(ItemState.INFO, in_place))
    if preview.selection.differences and preview.request.operation is Operation.COPY:
        lines.append(
            ChecklistItem(
                ItemState.INFO,
                "The folder differs from the database entry: "
                + " ".join(preview.selection.differences),
            )
        )
    lines.append(ChecklistItem(ItemState.INFO, _hash_text(preview)))
    if preview.request.operation is Operation.ARCHIVE:
        lines.append(ChecklistItem(ItemState.INFO, CHECK_AFTER_ARCHIVE_TEXT))
    side = preview.selection.side_files
    if side:
        names = ", ".join(f.rel_path for f in side)
        lines.append(
            ChecklistItem(
                ItemState.INFO,
                f"Also copied: {files_text(len(side))} from the recording folder itself, "
                f"such as the recorder's logs: {names}.",
            )
        )
    missing = missing_lines(preview)
    est = preview.estimate
    return PreviewSummary(
        files=f"{preview.selection.n_files:,}",
        size=format_size(preview.selection.total_bytes),
        missing="none" if not missing else "; ".join(missing),
        time=f"{duration_text(est.total_s)} at {speed_mb_s:g} MB/s",
        lines=tuple(lines),
    )


def file_list(preview: Preview, limit: int = FILES_LISTED) -> list[str]:
    """The first `limit` files to copy, then a count of the rest."""
    names = [f.rel_path for f in preview.selection.files]
    shown = names[:limit]
    if len(names) > limit:
        shown.append(f"and {len(names) - limit:,} more")
    return shown


# ---------------------------------------------------------------------------
# The laptop copy after an archive (D55)
# ---------------------------------------------------------------------------


class LaptopStep(StrEnum):
    NONE = "none"  # no passed archive at the recording's location
    CHECK_NEEDED = "check needed"
    READY = "ready"  # the check before delete passed
    PARTLY_DELETED = "partly deleted"
    DELETED = "deleted"


@dataclass(frozen=True, kw_only=True)
class LaptopCopy:
    """checked is True when a check before delete of the archive passed (D55)."""

    step: LaptopStep
    archive: TransferEntry | None
    text: str
    files_left: int | None = None
    checked: bool = False

    @property
    def can_check(self) -> bool:
        return self.step in (LaptopStep.CHECK_NEEDED, LaptopStep.READY, LaptopStep.PARTLY_DELETED)

    @property
    def can_delete(self) -> bool:
        return self.checked and self.step in (LaptopStep.READY, LaptopStep.PARTLY_DELETED)


def current_archive(rec: Recording, transfers: Iterable[TransferEntry]) -> TransferEntry | None:
    """The latest passed archive whose destination is where the recording points."""
    if rec.id is None:
        return None
    here = PureWindowsPath(join_location(rec.storage_root, rec.rel_path))
    found = None
    for t in sorted(transfers, key=lambda t: t.id or 0):
        if (
            t.operation is Operation.ARCHIVE
            and t.verification is Verification.PASS
            and t.finished_at is not None
            and t.destination is not None
            and PureWindowsPath(t.destination) == here
        ):
            found = t
    return found


def laptop_copy(rec: Recording, transfers: Sequence[TransferEntry]) -> LaptopCopy:
    """Where the laptop copy stands after the recording's archive (D52, D55)."""
    archive = current_archive(rec, transfers)
    if archive is None:
        return LaptopCopy(step=LaptopStep.NONE, archive=None, text="")
    deletes = [
        t
        for t in transfers
        if t.operation is Operation.DELETE and t.parent_id == archive.id and t.finished_at
    ]
    deleted = sum(t.n_files or 0 for t in deletes)
    # A passed delete left no listed file in the laptop folder. It counts only the files
    # it deleted, not those already gone, so the count alone can stay short.
    complete = any(t.verification is Verification.PASS for t in deletes)
    total = archive.n_files
    checked = checked_before_delete(archive, transfers)
    folder = archive.source
    if complete or (total is not None and deleted >= total):
        return LaptopCopy(
            step=LaptopStep.DELETED,
            archive=archive,
            text=f"The laptop copy in {folder} was deleted.",
            files_left=0,
        )
    if deleted:
        left = None if total is None else total - deleted
        if left is None:
            remain = "Some files remain"
        else:
            remain = f"{files_text(left)} {'remains' if left == 1 else 'remain'}"
        then = (
            'Click "Delete laptop copy" for the rest.'
            if checked
            else 'Click "Check before delete", then "Delete laptop copy" for the rest.'
        )
        return LaptopCopy(
            step=LaptopStep.PARTLY_DELETED,
            archive=archive,
            text=f"Partly deleted: {remain} in {folder}. {then}",
            files_left=left,
            checked=checked,
        )
    if checked:
        return LaptopCopy(
            step=LaptopStep.READY,
            archive=archive,
            text=(
                f"The NAS copy passed the check before delete. The laptop copy in {folder} "
                "can be deleted."
            ),
            checked=True,
        )
    return LaptopCopy(
        step=LaptopStep.CHECK_NEEDED,
        archive=archive,
        text=(
            f"The laptop copy in {folder} is still there. Before it can be deleted, "
            '"Check before delete" reads the NAS copy again, past this PC\'s file cache.'
        ),
    )


# ---------------------------------------------------------------------------
# Check before delete straight after an archive (D97)
# ---------------------------------------------------------------------------

CHECK_PHASE = '"Check before delete": reading the NAS copy'


@dataclass(frozen=True, kw_only=True)
class ArchiveCheck:
    """Check before delete run straight after a passed archive.

    passed is True only when the check passed. Otherwise why says what happened, for the
    note "Archived, check needed" (D85).
    """

    passed: bool
    why: str = ""


def check_after_archive(
    db_path: Path | str,
    archive_id: int,
    hash_mode: HashMode,
    *,
    sample_fraction: float,
    performed_by: str,
    progress: Callable[[VerifyProgress], None] | None,
    cancelled: Callable[[], bool],
) -> ArchiveCheck:
    """Run Check before delete (D55) on an archive that just passed (D97).

    Called by Run archive in the form and by the queue. A stop, a failed check, or a
    check that cannot run give passed False with the reason. "Sizes only" reads no file
    content, so the check is not run for it.
    """
    if hash_mode is HashMode.NONE:
        return ArchiveCheck(
            passed=False, why=f'"Check before delete" was not run: {CHECK_NEEDS_HASHES}'
        )
    try:
        check = check_before_delete(
            db_path,
            archive_id,
            hash_mode=hash_mode,
            sample_fraction=sample_fraction,
            performed_by=performed_by,
            progress=progress,
            cancelled=cancelled,
        )
    except DeleteRefused as exc:
        return ArchiveCheck(
            passed=False, why=f'"Check before delete" could not run: {" ".join(exc.reasons)}'
        )
    except Exception as exc:
        # The archive passed, so any error here, a locked database among them, leaves a
        # check still to do. It is not a failed archive (review of 1.1.0, finding 1).
        return ArchiveCheck(passed=False, why=f'"Check before delete" could not run: {exc}')
    if check.verification is Verification.PASS:
        return ArchiveCheck(passed=True)
    if check.verification is Verification.SKIPPED:
        return ArchiveCheck(
            passed=False, why=f'"Check before delete" was stopped. {check.notes or ""}'.strip()
        )
    return ArchiveCheck(passed=False, why=f'"Check before delete" failed: {check.notes}')


def check_needed_note(transfer_id: int | None, why: str) -> str:
    """The note of an archive that passed but whose check did not (D85, D97)."""
    return (
        f"Archived: transfer {transfer_id} passed its check, and the recording now points "
        f'at the NAS copy. The laptop copy stays. {why} Click "Check before delete" on the '
        '"Archive" page; the laptop copy can be deleted only after it passes.'
    )


# ---------------------------------------------------------------------------
# The tab's pages (D96)
# ---------------------------------------------------------------------------


class Page(StrEnum):
    """The pages of the Archive / copy tab, in their order on screen."""

    ARCHIVE = "Archive"
    CHECK = "Check"
    COPY = "Copy"


def page_for(rec: Recording, transfers: Sequence[TransferEntry]) -> Page:
    """The page that the Viewer's Archive / copy button opens (D96).

    Archive for a recording on the laptop, and for one whose laptop copy the app
    archived and has not deleted yet, so that Check before delete and Delete laptop copy
    are at hand. Copy for any other recording.
    """
    if rec.archive_state is ArchiveState.LOCAL:
        return Page.ARCHIVE
    step = laptop_copy(rec, transfers).step
    if step in (LaptopStep.CHECK_NEEDED, LaptopStep.READY, LaptopStep.PARTLY_DELETED):
        return Page.ARCHIVE
    return Page.COPY


# ---------------------------------------------------------------------------
# Unfinished transfers, progress, speed and time left
# ---------------------------------------------------------------------------

NOT_FINISHED = (
    "Not finished. The app stopped before the end, or the transfer still runs on another PC."
)


def load_unfinished(db_path: Path | str, performed_by: str | None) -> list[TransferEntry]:
    """Copies and archives the user may resume, newest first. None lists every user's."""
    with open_db(db_path, readonly=True) as conn:
        return repository.list_unfinished_transfers(conn, performed_by)


def forget_transfer(db_path: Path | str, transfer_id: int, *, now: str) -> None:
    """Hide an unfinished copy or archive from the list ("Forget"). Its row stays."""
    write_transaction(
        db_path, lambda conn: repository.dismiss_transfer(conn, transfer_id, dismissed_at=now)
    )


def unfinished_state(entry: TransferEntry) -> str:
    """'Stopped', 'Failed' or the not-finished text, for the list of unfinished
    transfers. The row's note gives the detail."""
    if entry.finished_at is None:
        return NOT_FINISHED
    if entry.verification is Verification.SKIPPED:
        return "Stopped"
    return "Failed"


def operation_name(operation: Operation) -> str:
    return "Archive to the NAS" if operation is Operation.ARCHIVE else "Copy to a PC"


def copy_progress_text(p: CopyProgress) -> str:
    """'412 of 1,194 files, 98.2 GB of 238.8 GB'."""
    return (
        f"{p.files_done:,} of {p.files_total:,} files, "
        f"{format_size(p.bytes_done)} of {format_size(p.bytes_total)}"
    )


def verify_progress_text(p: VerifyProgress) -> str:
    """'Checked 40 of 1,194 files, hashed 1.2 GB of 12.0 GB'."""
    text = f"Checked {p.files_done:,} of {p.files_total:,} files"
    if p.bytes_total:
        text += f", hashed {format_size(p.bytes_done)} of {format_size(p.bytes_total)}"
    return text


def percent(done: int, total: int) -> int:
    """Whole percent done, 0 for an empty total."""
    return 0 if total <= 0 else min(100, math.floor(100 * done / total))


class RateMeter:
    """Speed over the last SPEED_WINDOW_S seconds, and the time left at that speed."""

    def __init__(self, window_s: float = SPEED_WINDOW_S) -> None:
        self._window = window_s
        self._samples: deque[tuple[float, int]] = deque()

    def add(self, t: float, done: int) -> None:
        """Record `done` units (bytes) at time t (seconds, any clock that only rises)."""
        self._samples.append((t, done))
        while len(self._samples) > 2 and t - self._samples[1][0] >= self._window:
            self._samples.popleft()

    def rate(self) -> float | None:
        """Units per second, or None before two samples a moment apart."""
        if len(self._samples) < 2:
            return None
        (t0, d0), (t1, d1) = self._samples[0], self._samples[-1]
        if t1 - t0 <= 0:
            return None
        return max(0.0, (d1 - d0) / (t1 - t0))

    def seconds_left(self, total: int) -> float | None:
        rate = self.rate()
        if not rate or not self._samples:
            return None
        return max(0.0, (total - self._samples[-1][1]) / rate)


def speed_text(meter: RateMeter, total: int) -> str:
    """'85.3 MB/s, about 12 min left', or '' before the speed is known."""
    rate = meter.rate()
    left = meter.seconds_left(total)
    if rate is None or left is None:
        return ""
    return f"{rate / 1e6:.1f} MB/s, {duration_text(left)} left"
