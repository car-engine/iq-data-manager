"""The queue of the Archive / copy tab: transfers that run one after another (D81).

An item holds a whole TransferRequest, with its own operation, destination,
channels, range and check mode, or a Check archive of one recording (O41). The queue
lives in memory; a stopped item stays under "Unfinished transfers" as before.

run_item() runs one item with the functions the tab already uses: preview_transfer(),
run_transfer(), movecopy.check_after_archive() (which runs check_before_delete()) and
check_archive(). It adds no file code of its own. Pause stops the running item between
chunks, as Stop does; the next run of that item previews again and skips the files
already in place (D51, D63). No Qt here.
"""

import ntpath
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from iqdm.config import Config
from iqdm.db import repository
from iqdm.db.connection import open_db
from iqdm.models import ArchiveState, HashMode, Operation, Recording, Verification
from iqdm.movecopy import (
    CHECK_PHASE,
    Page,
    check_after_archive,
    check_needed_note,
    default_copy_destination,
)
from iqdm.scan.scanner import ScanCancelled, ScanError
from iqdm.timeutil import display_time
from iqdm.transfer.operations import (
    TransferRequest,
    check_archive,
    preview_transfer,
    run_transfer,
)
from iqdm.transfer.selection import SelectionError


class QueueError(ValueError):
    """An item cannot join the queue. The text is for the user."""


class QueueKind(StrEnum):
    ARCHIVE = "Archive"
    COPY = "Copy"
    CHECK_ARCHIVE = "Check archive"


class QueueState(StrEnum):
    WAITING = "Waiting"
    NEEDS_NAS_FOLDER = "Needs a NAS folder"  # added from the Viewer before the folder (D98)
    NEEDS_COPY_FOLDER = "Needs a copy folder"
    RUNNING = "Running"
    PAUSED = "Paused"
    DONE = "Done"
    CHECK_NEEDED = "Archived, check needed"  # the archive passed; its check did not (D85)
    FAILED = "Failed"
    NOT_STARTED = "Not started"


# An item that waits for its folder has no destination yet. Start does not run while
# one waits (D98).
NEEDS_FOLDER = frozenset({QueueState.NEEDS_NAS_FOLDER, QueueState.NEEDS_COPY_FOLDER})
FOLDER_STATE = {
    QueueKind.ARCHIVE: QueueState.NEEDS_NAS_FOLDER,
    QueueKind.COPY: QueueState.NEEDS_COPY_FOLDER,
}
ACTIVE = frozenset({QueueState.WAITING, QueueState.RUNNING, QueueState.PAUSED}) | NEEDS_FOLDER
# Clear finished removes these. An archive whose check is still needed stays, as a
# reminder that its laptop copy cannot be deleted yet (D85).
FINISHED = frozenset({QueueState.DONE, QueueState.FAILED, QueueState.NOT_STARTED})


@dataclass(frozen=True, kw_only=True)
class QueueItem:
    key: int = 0  # set by the queue
    recording_id: int
    label: str  # the recording as the table shows it
    kind: QueueKind
    request: TransferRequest | None = None  # None for Check archive
    state: QueueState = QueueState.WAITING
    note: str = ""  # a problem found when the item was added, or the result
    size_bytes: int | None = None  # from a preview
    transfer_id: int | None = None
    # When the entry was logged. A deleted entry's number can go to a new entry
    # (O52); the item runs only for the entry it was made for.
    created_at: str | None = None
    # The recording's relative path, for the destination of an item that waits for
    # its folder (D98).
    rel_path: str = ""

    @property
    def destination(self) -> str:
        return "" if self.request is None else self.request.destination


@dataclass(frozen=True)
class Phase:
    """Progress report: the step that starts now."""

    text: str


@dataclass(frozen=True, kw_only=True)
class ItemResult:
    state: QueueState
    note: str
    transfer_id: int | None = None
    size_bytes: int | None = None


# ---------------------------------------------------------------------------
# The list
# ---------------------------------------------------------------------------


class TransferQueue:
    """The items in their order. Keys stay the same while an item is in the queue."""

    def __init__(self) -> None:
        self._items: list[QueueItem] = []
        self._next_key = 1

    @property
    def items(self) -> list[QueueItem]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def get(self, key: int) -> QueueItem:
        return next(i for i in self._items if i.key == key)

    def position(self, key: int) -> int:
        return next(n for n, i in enumerate(self._items) if i.key == key)

    def add(self, item: QueueItem, position: int | None = None) -> QueueItem:
        """Add an item at the end, or at `position`. Refuses a repeat of an active item."""
        problem = self.duplicate_problem(item)
        if problem:
            raise QueueError(problem)
        added = replace(item, key=self._next_key)
        self._next_key += 1
        if position is None or position >= len(self._items):
            self._items.append(added)
        else:
            self._items.insert(max(0, position), added)
        return added

    def duplicate_problem(self, item: QueueItem) -> str:
        """Why `item` repeats an item that is waiting, running or paused, or ''.

        An archive or a Check archive of the same recording repeats. Two copies of one
        recording to different folders do not, for example two channels to two places.
        Any item to the same destination folder repeats.
        """
        other = self._repeated_by(item)
        if other is None:
            return ""
        same_recording = other.recording_id == item.recording_id and other.kind is item.kind
        if same_recording and (item.kind is not QueueKind.COPY or not item.destination):
            return f"Recording {item.recording_id} is already in the queue for this."
        return f"Another item in the queue already goes to {item.destination}."

    def holding(self, request: TransferRequest) -> QueueItem | None:
        """The waiting, running or paused item that a run of `request` in the form repeats.

        The form does not run such a transfer: the queue continues it (D86).
        """
        kind = QueueKind.ARCHIVE if request.operation is Operation.ARCHIVE else QueueKind.COPY
        return self._repeated_by(
            QueueItem(recording_id=request.recording_id, label="", kind=kind, request=request)
        )

    def _repeated_by(self, item: QueueItem, exclude: int | None = None) -> QueueItem | None:
        """The first active item that `item` repeats, by the rules of duplicate_problem().

        Two copies of one recording that both wait for the copy folder repeat, because
        the folder would give them the same destination (D98). `exclude` is the key of
        an item to leave out, the item itself when its folder is filled in.
        """
        for other in self._items:
            if other.state not in ACTIVE or other.key == exclude:
                continue
            same_recording = other.recording_id == item.recording_id and other.kind is item.kind
            if same_recording and item.kind is not QueueKind.COPY:
                return other
            if same_recording and not item.destination and not other.destination:
                return other
            same_folder = ntpath.normcase(ntpath.normpath(other.destination)) == (
                ntpath.normcase(ntpath.normpath(item.destination))
            )
            if item.destination and other.destination and same_folder:
                return other
        return None

    def has_paused(self) -> bool:
        """True when an item waits to be resumed. The Start button then reads Resume."""
        return any(i.state is QueueState.PAUSED for i in self._items)

    def remove(self, key: int) -> QueueItem:
        """Take an item out of the queue. A running item cannot be removed."""
        item = self.get(key)
        if item.state is QueueState.RUNNING:
            raise QueueError('The running item cannot be removed. Click "Pause" first.')
        self._items.remove(item)
        return item

    def set_state(self, key: int, state: QueueState) -> QueueItem:
        n = self.position(key)
        self._items[n] = replace(self._items[n], state=state)
        return self._items[n]

    def set_result(self, key: int, result: ItemResult) -> QueueItem:
        """The state and note of a run or a preview. A size or ID it lacks stays."""
        n = self.position(key)
        old = self._items[n]
        self._items[n] = replace(
            old,
            state=result.state,
            note=result.note,
            transfer_id=result.transfer_id if result.transfer_id is not None else old.transfer_id,
            size_bytes=result.size_bytes if result.size_bytes is not None else old.size_bytes,
        )
        return self._items[n]

    def next_runnable(self) -> QueueItem | None:
        """The first item that is waiting or paused."""
        return next(
            (i for i in self._items if i.state in (QueueState.WAITING, QueueState.PAUSED)),
            None,
        )

    def clear_finished(self) -> int:
        before = len(self._items)
        self._items = [i for i in self._items if i.state not in FINISHED]
        return before - len(self._items)

    def runnable_count(self) -> int:
        return sum(1 for i in self._items if i.state in (QueueState.WAITING, QueueState.PAUSED))

    def waiting_for(self, state: QueueState) -> int:
        """How many items wait for the folder that `state` names (D98)."""
        return sum(1 for i in self._items if i.state is state)

    def waiting_for_folder(self) -> int:
        """How many items wait for a NAS folder or a copy folder. Start waits for them."""
        return sum(1 for i in self._items if i.state in NEEDS_FOLDER)

    def fill_folder(self, kind: QueueKind, folder: str) -> list[QueueItem]:
        """Give each item of `kind` that waits for its folder a destination (D98).

        The destination is `folder` plus the item's relative path, as when the folder
        was chosen before the item was added. The item then waits to run. An item whose
        new destination repeats an active item gets NOT_STARTED with the reason.
        Returns the items now waiting to run, for their previews.
        """
        state = FOLDER_STATE[kind]
        if not folder.strip():
            return []
        ready: list[QueueItem] = []
        for n, item in enumerate(self._items):
            if item.state is not state or item.request is None:
                continue
            destination = default_copy_destination(folder, item.rel_path)
            filled = replace(item, request=replace(item.request, destination=destination))
            other = self._repeated_by(filled, exclude=item.key)
            if other is not None:
                note = f"Another item in the queue already goes to {destination}."
                self._items[n] = replace(filled, state=QueueState.NOT_STARTED, note=note)
                continue
            self._items[n] = replace(filled, state=QueueState.WAITING, note="")
            ready.append(self._items[n])
        return ready


# ---------------------------------------------------------------------------
# Items from the Viewer
# ---------------------------------------------------------------------------


def recording_label(rec: Recording, site: str, offset_hours: float) -> str:
    start = "" if rec.start_unix is None else display_time(rec.start_unix, offset_hours)[:16]
    parts = [f"Recording {rec.id}", start, site]
    return " \N{MIDDLE DOT} ".join(p for p in parts if p)


def item_for_recording(
    rec: Recording,
    *,
    check_archive_only: bool,
    nas_folder: str,
    copy_folder: str,
    hash_mode: HashMode,
    label: str,
) -> QueueItem:
    """A queue item for a recording chosen in the Viewer (D81).

    A recording on the laptop is archived to `nas_folder` plus its relative path. An
    archived recording is copied to `copy_folder` plus its relative path (D60); the
    Copy page's folder starts from the setting (D96). Both take the whole recording.
    Without the folder, the item has no destination and waits for it (D98). With
    check_archive_only, the item is a Check archive (O41). Raises QueueError with a
    plain reason.
    """
    if rec.id is None:
        raise QueueError("The recording has no ID.")
    if check_archive_only:
        if rec.archive_state is not ArchiveState.ARCHIVED:
            raise QueueError(
                f"Recording {rec.id} is not archived, so it has no NAS folder to check."
            )
        return QueueItem(
            recording_id=rec.id,
            label=label,
            kind=QueueKind.CHECK_ARCHIVE,
            created_at=rec.created_at,
        )
    if rec.archive_state is ArchiveState.LOCAL:
        destination = default_copy_destination(nas_folder, rec.rel_path)
        operation, kind = Operation.ARCHIVE, QueueKind.ARCHIVE
    else:
        destination = default_copy_destination(copy_folder, rec.rel_path)
        operation, kind = Operation.COPY, QueueKind.COPY
    request = TransferRequest(
        recording_id=rec.id, operation=operation, destination=destination, hash_mode=hash_mode
    )
    return QueueItem(
        recording_id=rec.id,
        label=label,
        kind=kind,
        request=request,
        state=QueueState.WAITING if destination else FOLDER_STATE[kind],
        created_at=rec.created_at,
        rel_path=rec.rel_path,
    )


PAGE_PRIORITY = (  # the first rule that matches an added item wins (D99)
    (lambda i: i.state is QueueState.NEEDS_NAS_FOLDER, Page.ARCHIVE),
    (lambda i: i.state is QueueState.NEEDS_COPY_FOLDER, Page.COPY),
    (lambda i: i.kind is QueueKind.ARCHIVE, Page.ARCHIVE),
    (lambda i: i.kind is QueueKind.COPY, Page.COPY),
    (lambda i: i.kind is QueueKind.CHECK_ARCHIVE, Page.CHECK),
)


def page_after_add(items: Sequence[QueueItem]) -> Page | None:
    """The page the tab shows after items were added from the Viewer, or None (D99).

    A folder that items wait for comes first, because Start waits for it (D98): the
    NAS folder for archives, then the folder for copies. Then the page of the action:
    Archive, Copy, Check. A selection may hold archives and copies together.
    """
    for matches, page in PAGE_PRIORITY:
        if any(matches(i) for i in items):
            return page
    return None


def scope_text(item: QueueItem, offset_hours: float) -> str:
    """'Whole recording', or the channels and the range of a copy."""
    request = item.request
    if request is None:
        return "NAS folder against the catalogue"
    parts = []
    if request.channels is not None:
        parts.append("Ch " + ", ".join(str(c) for c in request.channels))
    if request.start_unix is not None and request.end_unix is not None:
        start = display_time(request.start_unix, offset_hours)
        end = display_time(request.end_unix, offset_hours)
        parts.append(f"{start} to {end}")
    return " \N{MIDDLE DOT} ".join(parts) or "Whole recording"


def state_text(item: QueueItem) -> str:
    return f"{item.state}: {item.note}" if item.note else str(item.state)


# ---------------------------------------------------------------------------
# Running one item
# ---------------------------------------------------------------------------


def preview_item(
    db_path: Path | str,
    item: QueueItem,
    config: Config,
    *,
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    preview_options: Mapping[str, Any] | None = None,
) -> ItemResult:
    """Preview an archive or a copy when it joins the queue. Writes nothing.

    The state stays WAITING. The note names a problem, which the preview before the run
    finds again unless it was fixed in between.
    """
    if item.request is None or not item.request.destination:
        return ItemResult(state=item.state, note=item.note)
    try:
        preview = preview_transfer(
            db_path,
            item.request,
            config,
            progress=progress,
            cancelled=cancelled,
            **dict(preview_options or {}),
        )
    except ScanCancelled:
        return ItemResult(state=QueueState.WAITING, note="")
    except ScanError as exc:
        return ItemResult(
            state=QueueState.WAITING, note="Cannot scan the folder: " + "; ".join(exc.problems)
        )
    except SelectionError as exc:
        return ItemResult(state=QueueState.WAITING, note=str(exc))
    size = preview.selection.total_bytes
    note = "" if preview.ok else " ".join(preview.errors)
    return ItemResult(state=QueueState.WAITING, note=note, size_bytes=size)


def entry_problem(db_path: Path | str, item: QueueItem) -> str | None:
    """Why the item must not run for the entry its number names now, or None (O52).

    An entry deleted on another PC (D89) gives its number to the next new entry when
    it was the newest. The creation time tells them apart. An item made without one
    is not checked.
    """
    if item.created_at is None:
        return None
    with open_db(db_path, readonly=True) as conn:
        stored = repository.created_at(conn, item.recording_id)
    if stored is None:
        return repository.gone_text(item.recording_id)
    if stored != item.created_at:
        return repository.reused_text(item.recording_id, "queue item")
    return None


def run_item(
    db_path: Path | str,
    item: QueueItem,
    config: Config,
    *,
    performed_by: str,
    manifests_dir: Path,
    report: Callable[[object], None],
    copy_report: Callable[[object], None] | None = None,
    cancelled: Callable[[], bool],
    preview_options: Mapping[str, Any] | None = None,
) -> ItemResult:
    """Run one item: preview, then copy or archive, then for an archive Check before
    delete (D81, D97).

    report gets Phase, scan counts (int), VerifyProgress and RetryNotice; copy_report
    gets CopyProgress, and defaults to report. A cancel gives PAUSED while the item can
    be continued, and a failed preview gives NOT_STARTED. Errors the operations raise
    for a plain reason give FAILED; other exceptions reach the caller. Once an archive
    passed, every error of its Check before delete gives CHECK_NEEDED (D85).
    """
    problem = entry_problem(db_path, item)
    if problem is not None:
        return ItemResult(state=QueueState.NOT_STARTED, note=problem)
    if item.kind is QueueKind.CHECK_ARCHIVE:
        return _run_check_archive(db_path, item, performed_by, report, cancelled)
    request = item.request
    if request is None:
        return ItemResult(state=QueueState.NOT_STARTED, note="The item has no transfer.")
    if not request.destination.strip():  # it waits for its folder (D98)
        page = '"NAS folder for archives" on the "Archive" page'
        if request.operation is Operation.COPY:
            page = '"Folder for copies" on the "Copy" page'
        return ItemResult(
            state=QueueState.NOT_STARTED, note=f"The item has no destination. Choose the {page}."
        )
    report(Phase("Scanning the source folder"))
    try:
        preview = preview_transfer(
            db_path,
            request,
            config,
            progress=report,
            cancelled=cancelled,
            **dict(preview_options or {}),
        )
    except ScanCancelled:
        return ItemResult(state=QueueState.PAUSED, note="Paused before the copy started.")
    except ScanError as exc:
        return ItemResult(
            state=QueueState.NOT_STARTED,
            note="Cannot scan the folder: " + "; ".join(exc.problems),
        )
    except SelectionError as exc:
        return ItemResult(state=QueueState.NOT_STARTED, note=str(exc))
    size = preview.selection.total_bytes
    if not preview.ok:
        return ItemResult(
            state=QueueState.NOT_STARTED, note=" ".join(preview.errors), size_bytes=size
        )
    if cancelled():
        return ItemResult(
            state=QueueState.PAUSED, note="Paused before the copy started.", size_bytes=size
        )
    report(Phase("Copying"))
    outcome = run_transfer(
        db_path,
        preview,
        performed_by=performed_by,
        manifests_dir=manifests_dir,
        workers=config.copy_workers,
        copy_progress=copy_report or report,
        verify_progress=report,
        copy_retry=report,
        cancelled=cancelled,
    )
    tid = outcome.transfer_id
    if outcome.verification is Verification.SKIPPED:
        note = f'{outcome.notes or "Stopped."} "Resume" continues it.'
        return ItemResult(state=QueueState.PAUSED, note=note, transfer_id=tid, size_bytes=size)
    if not outcome.passed:
        note = f"Transfer {tid}: {outcome.notes or 'the check after the copy failed.'}"
        return ItemResult(state=QueueState.FAILED, note=note, transfer_id=tid, size_bytes=size)
    done = f"Transfer {tid} passed its check."
    if request.operation is not Operation.ARCHIVE or tid is None:
        return ItemResult(state=QueueState.DONE, note=done, transfer_id=tid, size_bytes=size)
    # Check before delete runs straight after every archive (D97). "Sizes only" reads no
    # file content, so it gives "Archived, check needed" (D85).
    if request.hash_mode is not HashMode.NONE:
        report(Phase(CHECK_PHASE))
    after = check_after_archive(
        db_path,
        tid,
        request.hash_mode,
        sample_fraction=config.hash_sample_fraction,
        performed_by=performed_by,
        progress=report,
        cancelled=cancelled,
    )
    if after.passed:
        note = f'{done} "Check before delete" passed; the laptop copy can be deleted.'
        return ItemResult(state=QueueState.DONE, note=note, transfer_id=tid, size_bytes=size)
    return ItemResult(
        state=QueueState.CHECK_NEEDED,
        note=check_needed_note(tid, after.why),
        transfer_id=tid,
        size_bytes=size,
    )


def _run_check_archive(
    db_path: Path | str,
    item: QueueItem,
    performed_by: str,
    report: Callable[[object], None],
    cancelled: Callable[[], bool],
) -> ItemResult:
    report(Phase('"Check archive": scanning the NAS folder'))
    try:
        outcome = check_archive(
            db_path,
            item.recording_id,
            performed_by=performed_by,
            progress=report,
            cancelled=cancelled,
        )
    except ScanCancelled:
        return ItemResult(state=QueueState.PAUSED, note="Paused before the check finished.")
    state = QueueState.FAILED if outcome.verification is Verification.FAIL else QueueState.DONE
    return ItemResult(state=state, note=outcome.notes, transfer_id=outcome.transfer_id)
