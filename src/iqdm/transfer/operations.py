"""Copy, archive, check and delete flows with their transfer_log rows (SPEC section 8).

Each flow runs in a worker thread. Database work happens in short steps, each with
its own connection, never while files are being copied:

- preview_transfer() reads the recording, rescans its folder (D53), checks the
  destination (D50, D51) and estimates the time. It writes nothing.
- run_transfer() writes the transfer_log row with started_at, copies, verifies,
  writes the manifest and finishes the row. A passed archive also points the
  recording at the NAS copy in the same transaction (finish_archive). A cancelled
  transfer is finished as 'skipped' with a note. If the app stops before the end, the
  row keeps finished_at NULL.
- delete_laptop_copy() checks a passed archive and its manifest, writes the delete
  row, deletes the laptop files through delete.py and finishes the row (D52).
- check_archive() compares an archived recording's folder with its entry.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from iqdm.config import Config
from iqdm.db import repository
from iqdm.db.connection import Connection, open_db, write_transaction
from iqdm.location import (
    DriveResolver,
    Location,
    LocationError,
    mapped_drive_unc,
    split_location,
)
from iqdm.models import (
    ArchiveState,
    HashMode,
    Operation,
    Recording,
    TransferEntry,
    Verification,
)
from iqdm.scan.scanner import ScanError, scan_recording
from iqdm.timeutil import utc_now_iso
from iqdm.transfer.copier import CopyItem, CopyProgress, CopyResult, copy_files
from iqdm.transfer.delete import (
    DeleteRefused,
    DeleteResult,
    archive_problems,
    delete_source_files,
    prepare_delete,
)
from iqdm.transfer.estimate import Estimate, estimate
from iqdm.transfer.manifest import (
    Manifest,
    ManifestError,
    manifest_files,
    read_manifest,
    write_manifest,
)
from iqdm.transfer.pathcheck import (
    GB,
    DestinationCheck,
    DiskUsageFn,
    check_destination,
    files_text,
)
from iqdm.transfer.power import keep_awake
from iqdm.transfer.selection import Selection, select_files
from iqdm.transfer.verify import VerifyProgress, VerifyResult, hashed_paths, verify_copy
from iqdm.viewer import recording_folder, scan_differences

NAMES_IN_NOTES = 10  # file names listed in a transfer_log note

Clock = Callable[[], str]


class TransferError(Exception):
    """A transfer cannot start, for example because its preview has errors."""


@dataclass(frozen=True, kw_only=True)
class TransferRequest:
    """What the user asked for. channels None means all channels."""

    recording_id: int
    operation: Operation  # COPY or ARCHIVE
    destination: str
    hash_mode: HashMode
    channels: tuple[int, ...] | None = None
    start_unix: float | None = None
    end_unix: float | None = None


@dataclass(frozen=True, kw_only=True)
class Preview:
    """Everything shown before a transfer runs. ok is True when it may run.

    destination is the folder the transfer writes to. For an archive it is the NAS
    location (D14): a mapped drive letter is replaced by its UNC path, so the log
    row, the manifest and the recording name the same folder. location is that
    split for an archive, and None for a copy.
    """

    request: TransferRequest
    recording: Recording
    selection: Selection
    destination: str
    location: Location | None
    check: DestinationCheck
    estimate: Estimate
    hashed_files: int
    errors: tuple[str, ...]  # the operation's own rules, then the destination's
    sample_fraction: float

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def items(self) -> list[CopyItem]:
        return [CopyItem(rel_path=f.rel_path, size=f.size) for f in self.selection.files]


@dataclass(frozen=True, kw_only=True)
class TransferOutcome:
    transfer_id: int
    verification: Verification
    copy: CopyResult
    verify: VerifyResult | None
    manifest_path: Path | None
    notes: str | None

    @property
    def passed(self) -> bool:
        return self.verification is Verification.PASS


@dataclass(frozen=True, kw_only=True)
class DeleteOutcome:
    transfer_id: int
    result: DeleteResult


@dataclass(frozen=True, kw_only=True)
class CheckOutcome:
    transfer_id: int
    verification: Verification
    notes: str


def _names(names: list[str]) -> str:
    shown = ", ".join(names[:NAMES_IN_NOTES])
    more = f", and {len(names) - NAMES_IN_NOTES:,} more" if len(names) > NAMES_IN_NOTES else ""
    return shown + more


def _load_recording(db_path: Path | str, recording_id: int) -> Recording:
    with open_db(db_path, readonly=True) as conn:
        return repository.get_recording(conn, recording_id)


def _archive_location(
    destination: str, nas_roots: tuple[str, ...], resolve_drive: DriveResolver | None
) -> Location | None:
    """The NAS location of an archive's destination, or None if it is not under a NAS root.

    check_destination() names the problem in the second case.
    """
    try:
        location = split_location(destination, nas_roots, resolve_drive)
    except LocationError:
        return None
    return location if location.archive_state is ArchiveState.ARCHIVED else None


def _archive_errors(
    db_path: Path | str, rec: Recording, selection: Selection, location: Location | None
) -> list[str]:
    """The rules for "Archive to NAS" (D50)."""
    errors = []
    if rec.archive_state is not ArchiveState.LOCAL:
        errors.append("The recording is already archived.")
    if not selection.is_whole:
        errors.append("An archive takes the whole recording with all its channels.")
    if selection.differences:
        errors.append(
            "The folder differs from the database entry. Scan it again in the Log tab "
            "and save the entry first. " + " ".join(selection.differences)
        )
    if location is None:
        return errors
    with open_db(db_path, readonly=True) as conn:
        other = repository.find_recording_by_location(
            conn, location.storage_root, location.rel_path
        )
    if other is not None and other != rec.id:
        errors.append(f"Recording {other} is already logged at the destination folder.")
    return errors


def preview_transfer(
    db_path: Path | str,
    request: TransferRequest,
    config: Config,
    *,
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    resolve_drive: DriveResolver | None = mapped_drive_unc,
    disk_usage: DiskUsageFn | None = None,
    long_paths: bool | None = None,
) -> Preview:
    """Rescan the source, check the destination and estimate the time. Writes nothing.

    Raises the scanner's ScanError and ScanCancelled, and SelectionError.
    """
    if request.operation not in (Operation.COPY, Operation.ARCHIVE):
        raise ValueError(f"a transfer is a copy or an archive, got {request.operation}")
    rec = _load_recording(db_path, request.recording_id)
    selection = select_files(
        rec,
        channels=request.channels,
        start_unix=request.start_unix,
        end_unix=request.end_unix,
        progress=progress,
        cancelled=cancelled,
    )
    errors = []
    location = None
    destination = request.destination
    if request.operation is Operation.ARCHIVE:
        location = _archive_location(request.destination, config.nas_roots, resolve_drive)
        if location is not None:
            destination = location.full_path
        errors += _archive_errors(db_path, rec, selection, location)
    extra = {} if disk_usage is None else {"disk_usage": disk_usage}
    check = check_destination(
        selection,
        destination,
        operation=request.operation,
        margin_bytes=round(config.free_space_margin_gb * GB),
        nas_roots=config.nas_roots,
        resolve_drive=resolve_drive,
        long_paths=long_paths,
        **extra,
    )
    errors += check.errors
    sizes = {f.rel_path: f.size for f in selection.files}
    targets = hashed_paths(
        list(sizes), request.hash_mode, config.hash_sample_fraction, check.existing
    )
    est = estimate(
        bytes_to_copy=check.bytes_to_copy,
        hashed_bytes=sum(sizes[p] for p in targets),
        rehashed_source_bytes=sum(sizes[p] for p in targets & check.existing),
        speed_mb_s=config.network_speed_mb_s,
    )
    return Preview(
        request=request,
        recording=rec,
        selection=selection,
        destination=destination,
        location=location,
        check=check,
        estimate=est,
        hashed_files=len(targets),
        errors=tuple(errors),
        sample_fraction=config.hash_sample_fraction,
    )


def _finish(
    db_path: Path | str, transfer_id: int, now: Clock, verification: Verification, notes: str
) -> None:
    write_transaction(
        db_path,
        lambda conn: repository.finish_transfer(
            conn, transfer_id, finished_at=now(), verification=verification, notes=notes
        ),
    )


def _copy_failure_notes(copy: CopyResult) -> str:
    names = [f"{f.rel_path} ({f.message})" for f in copy.failed]
    return f"Could not copy {files_text(len(copy.failed))}: {_names(names)}"


def _verify_failure_notes(result: VerifyResult) -> str:
    names = [f"{p.rel_path} ({p.message})" for p in result.problems]
    return f"The check failed for {files_text(len(result.problems))}: {_names(names)}"


def run_transfer(
    db_path: Path | str,
    preview: Preview,
    *,
    performed_by: str,
    manifests_dir: Path,
    workers: int = 1,
    now: Clock = utc_now_iso,
    copy_progress: Callable[[CopyProgress], None] | None = None,
    verify_progress: Callable[[VerifyProgress], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> TransferOutcome:
    """Copy, verify, write the manifest and record the result. See the module text."""
    if not preview.ok:
        raise TransferError("The transfer has problems: " + " ".join(preview.errors))
    request, selection = preview.request, preview.selection
    location = preview.location
    if request.operation is Operation.ARCHIVE and location is None:
        raise TransferError("An archive needs a destination under a NAS location.")
    source, destination = selection.source, Path(preview.destination)
    entry = TransferEntry(
        recording_id=request.recording_id,
        operation=request.operation,
        source=str(source),
        destination=preview.destination,
        range_start_unix=selection.range_start_unix,
        range_end_unix=selection.range_end_unix,
        channels=selection.channel_indices,
        hash_mode=request.hash_mode,
        started_at=now(),
        performed_by=performed_by,
    )
    tid = write_transaction(db_path, lambda conn: repository.insert_transfer(conn, entry))
    items = preview.items

    def outcome(
        verification: Verification,
        notes: str | None,
        copy: CopyResult,
        verify: VerifyResult | None = None,
        manifest: Path | None = None,
    ) -> TransferOutcome:
        return TransferOutcome(
            transfer_id=tid,
            verification=verification,
            copy=copy,
            verify=verify,
            manifest_path=manifest,
            notes=notes,
        )

    with keep_awake():
        copy = copy_files(
            source,
            destination,
            items,
            hash_source=request.hash_mode is not HashMode.NONE,
            workers=workers,
            progress=copy_progress,
            cancelled=cancelled,
        )
        if copy.cancelled:
            done = len(copy.copied) + len(copy.skipped)
            notes = f"Cancelled after {done:,} of {len(items):,} files."
            _finish(db_path, tid, now, Verification.SKIPPED, notes)
            return outcome(Verification.SKIPPED, notes, copy)
        if copy.failed:
            notes = _copy_failure_notes(copy)
            _finish(db_path, tid, now, Verification.FAIL, notes)
            return outcome(Verification.FAIL, notes, copy)
        result = verify_copy(
            source,
            destination,
            items,
            hash_mode=request.hash_mode,
            sample_fraction=preview.sample_fraction,
            source_hashes=copy.source_hashes,
            skipped=copy.skipped,
            progress=verify_progress,
            cancelled=cancelled,
        )
    if result.cancelled:
        notes = "Cancelled during the check. The files are copied but not checked."
        _finish(db_path, tid, now, Verification.SKIPPED, notes)
        return outcome(Verification.SKIPPED, notes, copy, result)
    if not result.passed:
        notes = _verify_failure_notes(result)
        _finish(db_path, tid, now, Verification.FAIL, notes)
        return outcome(Verification.FAIL, notes, copy, result)

    finished_at = now()
    manifest = Manifest(
        transfer_id=tid,
        recording_id=request.recording_id,
        operation=request.operation,
        source=str(source),
        destination=preview.destination,
        range_start_unix=selection.range_start_unix,
        range_end_unix=selection.range_end_unix,
        channels=selection.channel_indices,
        hash_mode=request.hash_mode,
        created_at=finished_at,
        files=manifest_files([(i.rel_path, i.size) for i in items], dict(result.hashes)),
    )
    path, digest = write_manifest(manifest, manifests_dir)
    n_files, total_bytes = len(items), selection.total_bytes
    if location is not None:

        def finish(conn: Connection) -> None:
            repository.finish_archive(
                conn,
                tid,
                finished_at=finished_at,
                n_files=n_files,
                total_bytes=total_bytes,
                manifest_path=str(path),
                manifest_sha256=digest,
                storage_root=location.storage_root,
                rel_path=location.rel_path,
            )

    else:

        def finish(conn: Connection) -> None:
            repository.finish_transfer(
                conn,
                tid,
                finished_at=finished_at,
                verification=Verification.PASS,
                n_files=n_files,
                total_bytes=total_bytes,
                manifest_path=str(path),
                manifest_sha256=digest,
            )

    try:
        write_transaction(db_path, finish)
    except repository.AlreadyArchivedError:
        notes = (
            "Someone else archived this recording while this copy ran. "
            "The recording keeps the other archive copy."
        )
        _finish(db_path, tid, now, Verification.FAIL, notes)
        return outcome(Verification.FAIL, notes, copy, result, path)
    return outcome(Verification.PASS, None, copy, result, path)


def _delete_notes(result: DeleteResult) -> str:
    parts = [f"Deleted {files_text(len(result.deleted))} from the laptop."]
    if result.already_gone:
        parts.append(f"Already gone: {files_text(len(result.already_gone))}.")
    if result.kept:
        names = [f"{k.rel_path} ({k.reason})" for k in result.kept]
        parts.append(f"Kept {files_text(len(result.kept))}: {_names(names)}")
    if result.cancelled:
        parts.append("Cancelled before the end.")
    return " ".join(parts)


def _load_archive(
    db_path: Path | str, archive_id: int
) -> tuple[TransferEntry, Recording, list[TransferEntry], Manifest]:
    """The archive row, its recording and history, and its manifest read unchanged.

    Raises DeleteRefused when the archive has no manifest or the manifest cannot be used.
    """
    with open_db(db_path, readonly=True) as conn:
        archive = repository.get_transfer(conn, archive_id)
        rec = repository.get_recording(conn, archive.recording_id)
        transfers = repository.list_transfers(conn, archive.recording_id)
    if archive.manifest_path is None or archive.manifest_sha256 is None:
        raise DeleteRefused(["The archive copy has no file list."])
    try:
        manifest = read_manifest(Path(archive.manifest_path), archive.manifest_sha256)
    except ManifestError as exc:
        raise DeleteRefused([f"The file list cannot be used: {exc}"]) from exc
    return archive, rec, transfers, manifest


def _check_notes(result: VerifyResult, what: str) -> str:
    if result.cancelled:
        return "Cancelled during the check."
    if not result.passed:
        return _verify_failure_notes(result)
    hashed = len(result.hashes)
    return f"{what} {files_text(hashed)} hashed and equal." if hashed else what


def _finish_check(
    db_path: Path | str,
    tid: int,
    now: Clock,
    result: VerifyResult,
    items: list[CopyItem],
    notes: str,
) -> CheckOutcome:
    if result.cancelled:
        verification = Verification.SKIPPED
    else:
        verification = Verification.PASS if result.passed else Verification.FAIL
    write_transaction(
        db_path,
        lambda conn: repository.finish_transfer(
            conn,
            tid,
            finished_at=now(),
            verification=verification,
            n_files=len(items),
            total_bytes=sum(i.size for i in items),
            notes=notes,
        ),
    )
    return CheckOutcome(transfer_id=tid, verification=verification, notes=notes)


def check_before_delete(
    db_path: Path | str,
    archive_id: int,
    *,
    hash_mode: HashMode,
    sample_fraction: float,
    performed_by: str,
    now: Clock = utc_now_iso,
    progress: Callable[[VerifyProgress], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> CheckOutcome:
    """Read the NAS copy of a passed archive past the PC's file cache (D55).

    Each NAS file must have its manifest size. Hashed files are compared with the
    manifest's copy-time hash, or with a hash of the laptop file where the manifest
    holds none. The check is logged as a 'check' row with the archive in parent_id;
    a pass allows "Delete laptop copy". Raises DeleteRefused when the archive cannot
    lead to a delete at all.
    """
    archive, rec, _, manifest = _load_archive(db_path, archive_id)
    problems = archive_problems(archive, manifest, rec)
    if problems or archive.destination is None:
        raise DeleteRefused(problems)
    items = [CopyItem(rel_path=f.path, size=f.size) for f in manifest.files]
    entry = TransferEntry(
        recording_id=archive.recording_id,
        operation=Operation.CHECK,
        parent_id=archive_id,
        source=archive.source,
        destination=archive.destination,
        hash_mode=hash_mode,
        started_at=now(),
        performed_by=performed_by,
    )
    tid = write_transaction(db_path, lambda conn: repository.insert_transfer(conn, entry))
    with keep_awake():
        result = verify_copy(
            Path(archive.source),
            Path(archive.destination),
            items,
            hash_mode=hash_mode,
            sample_fraction=sample_fraction,
            source_hashes={f.path: f.sha256 for f in manifest.files if f.sha256},
            uncached=True,
            progress=progress,
            cancelled=cancelled,
        )
    notes = _check_notes(result, f"The NAS copy matches the file list: {files_text(len(items))}.")
    return _finish_check(db_path, tid, now, result, items, notes)


def compare_with_laptop(
    db_path: Path | str,
    recording_id: int,
    laptop_folder: Path,
    *,
    hash_mode: HashMode,
    sample_fraction: float,
    performed_by: str,
    now: Clock = utc_now_iso,
    scan_progress: Callable[[int], None] | None = None,
    progress: Callable[[VerifyProgress], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> CheckOutcome:
    """Compare an archived recording's NAS folder with a laptop folder (D56).

    Both folders are scanned. They must hold the same files with the same sizes;
    hashed files must have the same SHA-256. NAS files are read past the PC's file
    cache. The comparison is logged as a 'check' row with the laptop folder as source
    and the NAS folder as destination. A pass clears the "not verified" mark.
    Raises TransferError for a recording that is not archived, or for a laptop folder
    that is the NAS folder; the scanner's ScanError and ScanCancelled; SelectionError.
    """
    rec = _load_recording(db_path, recording_id)
    if rec.archive_state is not ArchiveState.ARCHIVED:
        raise TransferError("Only an archived recording can be compared with a laptop copy.")
    nas_folder = recording_folder(rec)
    if PureWindowsPath(laptop_folder) == PureWindowsPath(nas_folder):
        raise TransferError("Choose the laptop folder. This is the NAS folder itself.")
    laptop = select_files(rec, folder=laptop_folder, progress=scan_progress, cancelled=cancelled)
    nas = select_files(rec, progress=scan_progress, cancelled=cancelled)
    started_at = now()
    laptop_files = {f.rel_path: f.size for f in laptop.files}
    nas_files = {f.rel_path for f in nas.files}
    only_laptop = sorted(set(laptop_files) - nas_files)
    only_nas = sorted(nas_files - set(laptop_files))
    entry = TransferEntry(
        recording_id=recording_id,
        operation=Operation.CHECK,
        source=str(laptop_folder),
        destination=str(nas_folder),
        hash_mode=hash_mode,
        started_at=started_at,
        performed_by=performed_by,
    )
    tid = write_transaction(db_path, lambda conn: repository.insert_transfer(conn, entry))
    items = [CopyItem(rel_path=p, size=s) for p, s in laptop_files.items() if p in nas_files]
    with keep_awake():
        result = verify_copy(
            laptop_folder,
            nas_folder,
            items,
            hash_mode=hash_mode,
            sample_fraction=sample_fraction,
            uncached=True,
            progress=progress,
            cancelled=cancelled,
        )
    if (only_laptop or only_nas) and not result.cancelled:
        parts = []
        for where, names in (("the laptop", only_laptop), ("the NAS", only_nas)):
            if names:
                parts.append(f"Only on {where}: {files_text(len(names))}: {_names(names)}.")
        if not result.passed:
            parts.append(_verify_failure_notes(result))
        result = VerifyResult(passed=False, problems=result.problems, hashes=result.hashes)
        notes = " ".join(parts)
    else:
        notes = _check_notes(
            result, f"The NAS folder matches the laptop folder: {files_text(len(items))}."
        )
    return _finish_check(db_path, tid, now, result, items, notes)


def delete_laptop_copy(
    db_path: Path | str,
    archive_id: int,
    *,
    performed_by: str,
    now: Clock = utc_now_iso,
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> DeleteOutcome:
    """Delete the laptop copy after a passed archive, and record it (D52).

    Raises DeleteRefused when a precondition does not hold; nothing is deleted then.
    """
    archive, rec, transfers, manifest = _load_archive(db_path, archive_id)
    plan = prepare_delete(archive, manifest, rec, transfers)
    entry = TransferEntry(
        recording_id=rec.id or archive.recording_id,
        operation=Operation.DELETE,
        parent_id=archive_id,
        source=archive.source,
        started_at=now(),
        performed_by=performed_by,
    )
    tid = write_transaction(db_path, lambda conn: repository.insert_transfer(conn, entry))
    result = delete_source_files(plan, cancelled=cancelled, progress=progress)
    sizes = {f.path: f.size for f in plan.files}
    verification = Verification.PASS if result.complete else Verification.FAIL
    notes = _delete_notes(result)
    write_transaction(
        db_path,
        lambda conn: repository.finish_transfer(
            conn,
            tid,
            finished_at=now(),
            verification=verification,
            n_files=len(result.deleted),
            total_bytes=sum(sizes[p] for p in result.deleted),
            notes=notes,
        ),
    )
    return DeleteOutcome(transfer_id=tid, result=result)


def check_archive(
    db_path: Path | str,
    recording_id: int,
    *,
    performed_by: str,
    now: Clock = utc_now_iso,
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> CheckOutcome:
    """Compare an archived recording's folder with its entry, and record the check.

    Channels without stored counts (legacy entries) get them from the folder, and
    that check is logged as 'skipped'. A folder that cannot be scanned is a failed
    check. Raises TransferError for a recording that is not archived, and the
    scanner's ScanCancelled.
    """
    rec = _load_recording(db_path, recording_id)
    if rec.archive_state is not ArchiveState.ARCHIVED:
        raise TransferError("Only an archived recording can be checked.")
    folder = recording_folder(rec)
    started_at = now()
    counts: dict[int, tuple[int, int]] = {}
    n_files = total_bytes = None
    try:
        scan = scan_recording(folder, rec.file_duration_s, progress=progress, cancelled=cancelled)
    except ScanError as exc:
        verification, notes = Verification.FAIL, "Cannot scan the folder: " + " ".join(exc.problems)
    else:
        n_files = sum(c.n_files for c in scan.channels)
        total_bytes = sum(c.total_bytes for c in scan.channels)
        differences = scan_differences(rec, scan)
        found = {c.channel_index: c for c in scan.channels}
        counts = {
            c.channel_index: (found[c.channel_index].n_files, found[c.channel_index].total_bytes)
            for c in rec.channels
            if c.channel_index in found and (c.n_files is None or c.total_bytes is None)
        }
        if differences:
            verification, notes = Verification.FAIL, " ".join(differences)
            counts = {}
        elif counts:
            verification = Verification.SKIPPED
            notes = (
                "File counts and sizes were not in the database. "
                "They are now taken from the folder."
            )
        else:
            verification = Verification.PASS
            notes = "The folder matches the database entry."
    entry = TransferEntry(
        recording_id=recording_id,
        operation=Operation.CHECK,
        source=str(folder),
        hash_mode=HashMode.NONE,
        started_at=started_at,
        finished_at=now(),
        n_files=n_files,
        total_bytes=total_bytes,
        verification=verification,
        performed_by=performed_by,
        notes=notes,
    )

    def record(conn: Connection) -> int:
        if counts:
            repository.update_channel_counts(conn, recording_id, counts)
        return repository.insert_transfer(conn, entry)

    tid = write_transaction(db_path, record)
    return CheckOutcome(transfer_id=tid, verification=verification, notes=notes)
