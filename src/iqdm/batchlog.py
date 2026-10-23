"""Logging several folders with one set-up (DECISIONS.md D90), without Qt.

SPEC section 6, "Several folders". The Log tab holds the shared fields the user types
once: logged by, site, project, plan reference, remarks, the format and the RF chain.
Each folder adds what its own scan and recorder's log give: start and end, the
channels with fc, fs and band, the sample type, the log's RF chain rows and the file
duration from its file names (D21, D22, D82, D88). Those values always win over the
shared ones. Each folder gets the checklist of entry.checklist(), plus a line for a
folder in the same list with the same capture (D61). Each entry is saved in its own
transaction by entry.save_new().

A folder's checklist is cached by its form, so typing in a field that no check reads
(remarks, plan reference) costs nothing. One folder of 2 channels by 7,200 files
takes about 3 ms (O51 probe).
"""

import itertools
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from iqdm import entry, recorderlog
from iqdm.db.connection import DatabaseError
from iqdm.entry import ChannelInput, ChecklistItem, EntryInput, ItemState, ParamInput
from iqdm.location import DriveResolver, Location, LocationError, split_location
from iqdm.models import Recording, SameStart, SampleType
from iqdm.scan.scanner import DEFAULT_EXTENSIONS, ScanError, ScanResult, scan_recording
from iqdm.timeutil import display_time, offset_label

DEFAULT_FILE_DURATION_S = 1.0
DURATION_RANGE_S = (0.001, 86400.0)  # the Log tab's file duration field
_CHANNEL_FOLDER_RE = re.compile(r"^(0|[1-9][0-9]*)$", re.ASCII)  # D11
_DATA_STEM_RE = re.compile(r"^\d+(\.\d+)?$", re.ASCII)

_keys = itertools.count(1)


@dataclass(eq=False)
class BatchFolder:
    """One folder of the list, with what its scan and its recorder's log gave.

    channels holds the channel values by index, with their marks: from the log, filled
    in from the file size or from fc, or typed by the user (D21, D82, D88). key stays
    the same for the folder while it is in the list.
    """

    path: str
    key: int = field(default_factory=lambda: next(_keys))
    ticked: bool = True
    scanned: bool = False
    location: Location | None = None
    location_error: str | None = None
    scan: ScanResult | None = None  # at file_duration_s
    scan_problems: tuple[str, ...] = ()
    recorder: recorderlog.RecorderLog | None = None
    log_dtype: SampleType | None = None
    file_duration_s: float = DEFAULT_FILE_DURATION_S
    duration_inferred: bool = False
    logged_id: int | None = None
    duplicate_checked: bool = False
    same_start: tuple[SameStart, ...] = ()
    db_error: str | None = None
    channels: dict[int, ChannelInput] = field(default_factory=dict)
    saved_id: int | None = None
    save_error: str | None = None

    @property
    def name(self) -> str:
        return Path(self.path).name or self.path

    @property
    def saved(self) -> bool:
        return self.saved_id is not None

    def start_unix(self) -> float | None:
        return None if self.scan is None else entry.scan_start(self.scan)


# ---------------------------------------------------------------------------
# Choosing folders
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Candidates:
    """The subfolders of a parent that look like recordings.

    parent_is_recording is True when the parent itself holds channel folders or data
    files: it is then one recording, and its subfolders are channel folders.
    """

    parent: Path
    folders: tuple[Path, ...]
    parent_is_recording: bool


def _is_data_file(name: str) -> bool:
    stem, dot, ext = name.rpartition(".")
    return bool(dot) and f".{ext}".lower() in DEFAULT_EXTENSIONS and bool(_DATA_STEM_RE.match(stem))


def looks_like_recording(folder: Path) -> bool:
    """True when the folder holds a channel folder or a data file at its top (D11)."""
    try:
        with os.scandir(folder) as entries:
            for e in entries:
                if e.is_dir(follow_symlinks=False) and _CHANNEL_FOLDER_RE.match(e.name):
                    return True
                if e.is_file(follow_symlinks=False) and _is_data_file(e.name):
                    return True
    except OSError:
        return False
    return False


def list_candidates(parent: Path) -> Candidates:
    """The parent's subfolders that look like recordings, sorted by name.

    Raises OSError when the parent cannot be read. Reads one level below each
    subfolder only, so it is quick on the NAS; the scan decides the rest.
    """
    with os.scandir(parent) as entries:
        subfolders = sorted(
            (Path(e.path) for e in entries if e.is_dir(follow_symlinks=False)),
            key=lambda p: p.name.casefold(),
        )
    found = tuple(
        p for p in subfolders if not _CHANNEL_FOLDER_RE.match(p.name) and looks_like_recording(p)
    )
    return Candidates(
        parent=parent, folders=found, parent_is_recording=looks_like_recording(parent)
    )


def same_folder(a: str, b: str) -> bool:
    """Two folder texts that name one folder, compared without letter case (Windows)."""
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


# ---------------------------------------------------------------------------
# Scanning one folder (in a worker)
# ---------------------------------------------------------------------------


def _duration_from_names(scan: ScanResult) -> tuple[float, bool]:
    """The file duration from the file names (D22), and whether it differs from 1 s."""
    spacing = entry.typical_spacing(scan)
    low, high = DURATION_RANGE_S
    if spacing is None or not low <= spacing <= high:
        return DEFAULT_FILE_DURATION_S, False
    return spacing, spacing != DEFAULT_FILE_DURATION_S


def scan_folder(
    folder: BatchFolder,
    *,
    nas_roots: Sequence[str],
    resolve_drive: DriveResolver | None,
    db_path: str | None,
    known_param_names: Sequence[str] = (),
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> BatchFolder:
    """The folder after its scan, its recorder's log and the catalogue checks.

    Returns a new BatchFolder with the same key. A folder that cannot be logged or
    scanned comes back with its reason. Raises ScanCancelled when cancelled() is True.
    """
    out = replace(
        folder,
        scanned=True,
        scan=None,
        scan_problems=(),
        recorder=None,
        log_dtype=None,
        logged_id=None,
        duplicate_checked=False,
        same_start=(),
        db_error=None,
        channels={},
        save_error=None,
    )
    try:
        out.location = split_location(folder.path, nas_roots, resolve_drive)
        out.location_error = None
    except LocationError as exc:
        out.location, out.location_error = None, str(exc)
        return out
    try:
        raw = scan_recording(Path(folder.path), 1.0, progress=progress, cancelled=cancelled)
    except ScanError as exc:
        out.scan_problems = exc.problems
        return out
    except OSError as exc:
        out.scan_problems = (str(exc),)
        return out
    out.file_duration_s, out.duration_inferred = _duration_from_names(raw)
    out.scan = entry.with_file_duration(raw, out.file_duration_s)
    for channel in out.scan.channels:
        # Count sizes and close pairs here, in the worker, so the checklists on the
        # main thread find them done.
        _ = (channel.size_counts, channel.body_size_counts, channel.close_pairs, channel.gaps)
    log = recorderlog.read_folder(Path(folder.path), [f.name for f in raw.side_files])
    out.recorder = log if log.found or log.problems else None
    indices = [c.channel_index for c in out.scan.channels]
    values = recorderlog.form_values(log, indices, [], known_param_names) if log.found else None
    out.log_dtype = None if values is None else values.dtype
    for index in indices:
        fc = "" if values is None else values.fc_mhz.get(index, "")
        fs = "" if values is None else values.fs_text.get(index, "")
        band = entry.band_for_fc(fc)
        out.channels[index] = ChannelInput(
            channel_index=index,
            band="" if band is None else band.name,
            fc_mhz=fc,
            fs_text=fs,
            fc_from_log=bool(fc),
            fs_from_log=bool(fs),
            band_from_fc=band is not None,
        )
    if db_path and out.location is not None:
        try:
            out.logged_id = entry.find_logged(db_path, out.location)
            out.same_start = tuple(entry.find_same_start(db_path, out.scan))
            out.duplicate_checked = True
        except (DatabaseError, OSError) as exc:
            out.db_error = str(exc)
    return out


# ---------------------------------------------------------------------------
# The form and the checklist of one folder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FolderView:
    """One folder's form, what its log filled in, and its checklist."""

    form: EntryInput
    log_values: recorderlog.FormValues | None
    items: tuple[ChecklistItem, ...]


def form_for(
    shared: EntryInput, folder: BatchFolder, known_param_names: Sequence[str] = ()
) -> tuple[EntryInput, recorderlog.FormValues | None]:
    """The folder's entry: the shared fields with the folder's own values in place.

    The log's sample type and RF chain rows win over the shared ones (D82). fs follows
    the file size, the sample type and the header while it was filled in or is empty
    (D21).
    """
    scan = folder.scan
    if scan is None:
        return replace(shared, channels=[]), None
    dtype = folder.log_dtype or shared.dtype
    duration = folder.file_duration_s
    channels = []
    for ch in scan.channels:
        inp = folder.channels.get(ch.channel_index, ChannelInput(channel_index=ch.channel_index))
        if not inp.fs_from_log and (inp.fs_inferred or not inp.fs_text.strip()):
            result = entry.infer_fs(
                ch, dtype=dtype, header_bytes=shared.header_bytes, file_duration_s=duration
            )
            inp = replace(
                inp,
                fs_text="" if result.fs_hz is None else entry.format_frequency(result.fs_hz),
                fs_inferred=result.fs_hz is not None,
            )
        channels.append(inp)
    values = None
    params = list(shared.params)
    log = folder.recorder
    if log is not None and log.found:
        indices = [c.channel_index for c in scan.channels]
        values = recorderlog.form_values(log, indices, shared.params, known_param_names)
        if values.params:
            params = recorderlog.merge_params(shared.params, values.params)
    form = replace(
        shared,
        dtype=dtype,
        file_duration_s=duration,
        file_duration_inferred=folder.duration_inferred,
        channels=channels,
        params=params,
    )
    return form, values


@dataclass(frozen=True)
class LogShown:
    """What a folder's recorder's log adds to the shared fields, for the screen (O55).

    rows are the log's RF chain rows, saved with the folder. replaced are the shared
    rows of the same names, which the folder does not get (recorderlog.merge_params()).
    dtype is the log's sample type, or None when the log names none.
    """

    rows: tuple[ParamInput, ...]
    replaced: tuple[ParamInput, ...]
    dtype: SampleType | None


def log_shown(
    shared: EntryInput, folder: BatchFolder, known_param_names: Sequence[str] = ()
) -> LogShown | None:
    """The log rows and sample type that form_for() puts into the folder's entry.

    None for a folder that is not scanned or has no recorder's log with values.
    """
    log = folder.recorder
    if folder.scan is None or log is None or not log.found:
        return None
    indices = [c.channel_index for c in folder.scan.channels]
    values = recorderlog.form_values(log, indices, shared.params, known_param_names)
    names = {p.param.casefold() for p in values.params}
    replaced = tuple(p for p in shared.params if p.param.strip().casefold() in names)
    if not values.params and folder.log_dtype is None:
        return None
    return LogShown(rows=values.params, replaced=replaced, dtype=folder.log_dtype)


def _end_unix(scan: ScanResult, duration: float) -> float | None:
    ends = [c.files[-1].timestamp + duration for c in scan.channels if c.files]
    return max(ends) if ends else None


def _capture(folder: BatchFolder) -> tuple[float, float, tuple[int, ...]] | None:
    scan = folder.scan
    if scan is None:
        return None
    start, end = entry.scan_start(scan), _end_unix(scan, folder.file_duration_s)
    if start is None or end is None:
        return None
    return start, end, tuple(c.channel_index for c in scan.channels)


def same_capture_in_list(folder: BatchFolder, folders: Sequence[BatchFolder]) -> list[str]:
    """Names of other folders in the list with the same start, end and channels (D61)."""
    mine = _capture(folder)
    if mine is None:
        return []
    return [
        f.name
        for f in folders
        if f.key != folder.key and f.ticked and not f.saved and _capture(f) == mine
    ]


def folder_items(
    shared: EntryInput,
    folder: BatchFolder,
    folders: Sequence[BatchFolder],
    known_param_names: Sequence[str] = (),
) -> FolderView:
    """One folder's form and checklist, as the one-folder form would show it."""
    if not folder.scanned:
        return FolderView(
            replace(shared, channels=[]), None, (ChecklistItem(ItemState.TODO, "Scan the folder"),)
        )
    form, values = form_for(shared, folder, known_param_names)
    filled = () if values is None else recorderlog.still_filled(values, form)
    extra = recorderlog.checklist_items(folder.recorder, folder.scan, filled)
    extra += [
        ChecklistItem(
            ItemState.INFO,
            f"{name} in this list has the same start, end and channels. It may be the same "
            "capture in another folder.",
        )
        for name in same_capture_in_list(folder, folders)
    ]
    if folder.db_error is not None:
        extra.append(
            ChecklistItem(
                ItemState.ERROR, f"Cannot check the database for this folder: {folder.db_error}"
            )
        )
    items = entry.checklist(
        form,
        scan=folder.scan,
        location=folder.location,
        location_error=folder.location_error,
        logged_id=folder.logged_id,
        duplicate_checked=folder.duplicate_checked,
        scan_problems=folder.scan_problems,
        known_param_names=known_param_names,
        same_start=folder.same_start,
        extra_items=extra,
    )
    return FolderView(form, values, tuple(items))


def _state_key(folder: BatchFolder) -> tuple[object, ...]:
    """What a folder's checklist depends on. A scan and a log are new objects after a
    rescan, so they compare by identity; their text would be large."""
    return (
        folder.scanned,
        id(folder.scan),
        id(folder.recorder),
        folder.location,
        folder.location_error,
        folder.scan_problems,
        folder.log_dtype,
        folder.file_duration_s,
        folder.duration_inferred,
        folder.logged_id,
        folder.duplicate_checked,
        folder.same_start,
        folder.db_error,
        repr(sorted(folder.channels.items())),
    )


class FolderChecks:
    """folder_items() with a cache by the folder's form and state.

    The remarks and the plan reference are left out of the cache key, because no
    check reads them.
    """

    def __init__(self) -> None:
        self._cache: dict[int, tuple[object, FolderView]] = {}

    def clear(self) -> None:
        self._cache.clear()

    def view(
        self,
        shared: EntryInput,
        folder: BatchFolder,
        folders: Sequence[BatchFolder],
        known_param_names: Sequence[str] = (),
    ) -> FolderView:
        key = (
            repr(replace(shared, remarks="", recording_plan_ref="", channels=[])),
            _state_key(folder),
            tuple(same_capture_in_list(folder, folders)),
            tuple(known_param_names),
        )
        cached = self._cache.get(folder.key)
        if cached is not None and cached[0] == key:
            view = cached[1]
            return replace(
                view,
                form=replace(
                    view.form,
                    remarks=shared.remarks,
                    recording_plan_ref=shared.recording_plan_ref,
                ),
            )
        view = folder_items(shared, folder, folders, known_param_names)
        self._cache[folder.key] = (key, view)
        return view


# ---------------------------------------------------------------------------
# The state of each folder and the checklist of the list
# ---------------------------------------------------------------------------


def _count(n: int, word: str, plural: str | None = None) -> str:
    """'1 error', '3 errors', '2 entries'."""
    return f"{n:,} {word if n == 1 else plural or word + 's'}"


def folder_state(folder: BatchFolder, items: Sequence[ChecklistItem]) -> tuple[ItemState, str]:
    """The state column of the folder table: a state for the mark and colour, and text."""
    if folder.saved:
        return ItemState.OK, f"Saved as recording {folder.saved_id}"
    if folder.save_error is not None:
        return ItemState.ERROR, f"Not saved: {folder.save_error}"
    if not folder.scanned:
        return ItemState.TODO, "Not scanned"
    errors = sum(1 for i in items if i.state is ItemState.ERROR)
    todo = sum(1 for i in items if i.state is ItemState.TODO)
    notes = sum(1 for i in items if i.state is ItemState.INFO)
    if errors:
        return ItemState.ERROR, _count(errors, "error")
    if todo:
        return ItemState.TODO, f"{todo:,} to do"
    if notes:
        return ItemState.INFO, f"Ready, {_count(notes, 'note')}"
    return ItemState.OK, "Ready"


def is_ready(folder: BatchFolder, items: Sequence[ChecklistItem]) -> bool:
    """True for a ticked folder, not yet saved, whose checklist allows a save."""
    return folder.ticked and folder.scanned and not folder.saved and entry.can_save(items)


def combined_items(
    views: Sequence[tuple[BatchFolder, FolderView]],
) -> list[ChecklistItem]:
    """The checklist of the list: what blocks the ticked folders, each problem once.

    A to-do item or an error that every ticked folder shares, such as "Choose a site",
    is listed once for all of them. Other to-do items and errors are listed with the
    folder's name. Information lines stay in the checklist of the selected folder.
    """
    if not views:
        return [ChecklistItem(ItemState.TODO, "Add folders, then scan them")]
    open_views = [(f, v) for f, v in views if f.ticked and not f.saved]
    if not open_views:
        if all(f.saved for f, _ in views):
            return [ChecklistItem(ItemState.OK, "Every folder in the list is saved")]
        return [ChecklistItem(ItemState.TODO, "Tick at least one folder to save")]
    items: list[ChecklistItem] = []
    scanned = [(f, v) for f, v in open_views if f.scanned]
    not_scanned = len(open_views) - len(scanned)
    if not_scanned:
        items.append(
            ChecklistItem(ItemState.TODO, f"Scan the folders: {not_scanned:,} not scanned yet")
        )
    ready = sum(1 for f, v in scanned if is_ready(f, v.items))
    state = ItemState.OK if ready == len(open_views) else ItemState.INFO
    ticked = _count(len(open_views), "ticked folder")
    items.append(ChecklistItem(state, f"{ready:,} of {ticked} ready to save"))
    blocking = (ItemState.ERROR, ItemState.TODO)
    shared: list[ChecklistItem] = []
    if len(scanned) > 1:
        first = [i for i in scanned[0][1].items if i.state in blocking]
        shared = [i for i in first if all(i in v.items for _, v in scanned[1:])]
    for item in shared:
        items.append(ChecklistItem(item.state, f"{item.text} (all {len(scanned):,} folders)"))
    for folder, view in scanned:
        for item in view.items:
            if item.state in blocking and item not in shared:
                items.append(ChecklistItem(item.state, f"{folder.name}: {item.text}"))
    return items


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SaveOutcome:
    key: int
    recording_id: int | None = None
    error: str | None = None


def build_recordings(
    views: Sequence[tuple[BatchFolder, FolderView]], known_param_names: Sequence[str] = ()
) -> tuple[list[tuple[int, Recording]], list[SaveOutcome]]:
    """The entries of the ready folders, and an outcome for each that cannot be built."""
    built: list[tuple[int, Recording]] = []
    failed: list[SaveOutcome] = []
    for folder, view in views:
        if not is_ready(folder, view.items):
            continue
        try:
            rec = entry.build_recording(
                view.form,
                scan=folder.scan,
                location=folder.location,
                known_param_names=known_param_names,
            )
        except ValueError as exc:
            failed.append(SaveOutcome(folder.key, error=str(exc)))
            continue
        built.append((folder.key, rec))
    return built, failed


def save_all(
    db_path: str,
    recordings: Sequence[tuple[int, Recording]],
    *,
    progress: Callable[[tuple[int, int]], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    save: Callable[[str, Recording], int] = entry.save_new,
) -> list[SaveOutcome]:
    """Save each entry in its own transaction, one after another.

    A failure, for example a folder logged meanwhile on another PC, is recorded for
    its folder, and the rest are saved. Cancel stops between two entries.
    progress((done, total)) is called before each entry.
    """
    outcomes: list[SaveOutcome] = []
    for n, (key, rec) in enumerate(recordings):
        if cancelled is not None and cancelled():
            break
        if progress is not None:
            progress((n, len(recordings)))
        try:
            outcomes.append(SaveOutcome(key, recording_id=save(db_path, rec)))
        except (DatabaseError, OSError, ValueError) as exc:
            outcomes.append(SaveOutcome(key, error=str(exc)))
    return outcomes


def save_question(
    views: Sequence[tuple[BatchFolder, FolderView]],
    *,
    site: str,
    project: str,
    logged_by: str,
    offset_hours: float,
) -> str:
    """The question before a save: what is saved with which shared values, and what not."""
    ready = [(f, v) for f, v in views if is_ready(f, v.items)]
    left_out = [f for f, v in views if not f.saved and not is_ready(f, v.items)]
    starts = [s for f, _ in ready if (s := f.start_unix()) is not None]
    ends = [
        e for f, _ in ready if f.scan is not None and (e := _end_unix(f.scan, f.file_duration_s))
    ]
    size = sum(c.total_bytes for f, _ in ready if f.scan is not None for c in f.scan.channels)
    span = ""
    if starts and ends:
        span = (
            f"From {display_time(min(starts), offset_hours)} to "
            f"{display_time(max(ends), offset_hours)} {offset_label(offset_hours)}, "
        )
    lines = [
        f"Save {_count(len(ready), 'entry', 'entries')}?",
        "",
        f"Site: {site or 'none'}. Project: {project or 'none'}. Logged by: {logged_by}.",
        f"{span}{entry.format_size(size)} in total.",
    ]
    if left_out:
        names = ", ".join(f.name for f in left_out[:5])
        more = f" and {len(left_out) - 5:,} more" if len(left_out) > 5 else ""
        lines += ["", f"Not saved now, unticked or not ready: {names}{more}."]
    lines += ["", "Each folder is saved as its own entry."]
    return "\n".join(lines)


def _recordings_text(ids: Sequence[int]) -> str:
    """'recording 120', 'recordings 120 to 130', 'recordings 120, 122'."""
    if len(ids) == 1:
        return f"recording {ids[0]}"
    if max(ids) - min(ids) == len(ids) - 1:
        return f"recordings {min(ids)} to {max(ids)}"
    return "recordings " + ", ".join(str(i) for i in ids)


def saved_text(outcomes: Sequence[SaveOutcome], names: dict[int, str]) -> tuple[ItemState, str]:
    """The message after a save, with its state: what was saved and which folders not."""
    ids = [o.recording_id for o in outcomes if o.recording_id is not None]
    failed = [o for o in outcomes if o.error is not None]
    parts = []
    if ids:
        parts.append(f"Saved {_count(len(ids), 'entry', 'entries')} ({_recordings_text(ids)}).")
    if failed:
        listed = "; ".join(f"{names.get(o.key, '?')}: {o.error}" for o in failed[:3])
        more = f"; and {len(failed) - 3:,} more" if len(failed) > 3 else ""
        parts.append(f"{len(failed):,} not saved: {listed}{more}")
    if not parts:
        return ItemState.INFO, "Nothing saved."
    if not failed:
        return ItemState.OK, " ".join(parts)
    return (ItemState.INFO if ids else ItemState.ERROR), " ".join(parts)
