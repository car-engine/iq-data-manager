"""The only module that deletes files (CLAUDE.md; SPEC section 8; DECISIONS.md D52).

It deletes the laptop copy of a recording after an archive to the NAS passed
verification. prepare_delete() refuses unless all of these hold:
- the archive finished with verification 'pass' and has a manifest;
- the manifest belongs to that archive, and the caller read it with
  manifest.read_manifest(path, archive.manifest_sha256), so it is unchanged;
- the recording is archived and points at the archive's destination;
- a check before delete of that archive passed, and it started after the archive
  finished (D55). That check read the NAS files past the PC's file cache.

delete_source_files() then works file by file. Right before a source file is
deleted, the NAS copy must be a regular file with the manifest size, and the source
file must be a regular file with the manifest size inside the source folder. A file
that fails a check is kept and reported. Only files listed in the manifest are
deleted. Afterwards, folders that held them, and the source folder itself, are
removed when they are empty. Nothing is deleted by pattern or by tree.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from iqdm.location import join_location
from iqdm.models import ArchiveState, Operation, Recording, TransferEntry, Verification
from iqdm.transfer.copier import local_path
from iqdm.transfer.manifest import Manifest, ManifestFile, safe_rel_path


class DeleteRefused(Exception):  # noqa: N818  (the user sees it as a refusal)
    """The preconditions for deleting the laptop copy do not hold. reasons lists them."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = tuple(reasons)
        super().__init__(" ".join(self.reasons))


@dataclass(frozen=True, kw_only=True)
class DeletePlan:
    """What delete_source_files() may delete: manifest files under `source`."""

    archive_id: int
    recording_id: int
    source: Path
    destination: Path
    files: tuple[ManifestFile, ...]


@dataclass(frozen=True, kw_only=True)
class KeptFile:
    rel_path: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class DeleteResult:
    deleted: tuple[str, ...]
    already_gone: tuple[str, ...]  # not in the source folder any more
    kept: tuple[KeptFile, ...]
    folders_removed: tuple[str, ...]  # '' is the source folder itself
    cancelled: bool = False

    @property
    def complete(self) -> bool:
        """True when no listed file remains in the source folder."""
        return not self.kept and not self.cancelled


def _same_path(a: str, b: str) -> bool:
    return PureWindowsPath(a) == PureWindowsPath(b)


NOT_CHECKED = (
    "The NAS copy has not passed \"Check before delete\" since it was archived. "
    "Run that check first."
)


def checked_before_delete(archive: TransferEntry, transfers: Iterable[TransferEntry]) -> bool:
    """True when a check before delete of `archive` passed after the archive finished."""
    if archive.id is None or archive.finished_at is None:
        return False
    return any(
        t.operation is Operation.CHECK
        and t.parent_id == archive.id
        and t.verification is Verification.PASS
        and t.finished_at is not None
        and t.started_at >= archive.finished_at
        for t in transfers
    )


def prepare_delete(
    archive: TransferEntry,
    manifest: Manifest,
    rec: Recording,
    transfers: Iterable[TransferEntry],
) -> DeletePlan:
    """Check the preconditions and return the plan. Raises DeleteRefused.

    transfers is the recording's transfer history, which holds the check before
    delete (D55).
    """
    reasons = archive_problems(archive, manifest, rec)
    if not checked_before_delete(archive, transfers):
        reasons.append(NOT_CHECKED)
    if reasons or archive.id is None or archive.destination is None:
        raise DeleteRefused(reasons)
    return DeletePlan(
        archive_id=archive.id,
        recording_id=archive.recording_id,
        source=Path(archive.source),
        destination=Path(archive.destination),
        files=manifest.files,
    )


def archive_problems(archive: TransferEntry, manifest: Manifest, rec: Recording) -> list[str]:
    """Why the archive cannot lead to a delete, apart from the check before delete.

    The check before delete itself needs the same conditions.
    """
    reasons = []
    if archive.id is None:
        reasons.append("The archive copy has no entry in the transfer history.")
    if archive.operation is not Operation.ARCHIVE:
        reasons.append("Only the laptop copy of an archived recording can be deleted.")
    if archive.finished_at is None or archive.verification is not Verification.PASS:
        reasons.append("The archive copy did not pass its check.")
    if archive.manifest_path is None or archive.manifest_sha256 is None:
        reasons.append("The archive copy has no file list.")
    if (
        manifest.transfer_id != archive.id
        or manifest.recording_id != archive.recording_id
        or manifest.operation is not Operation.ARCHIVE
        or not _same_path(manifest.source, archive.source)
        or archive.destination is None
        or not _same_path(manifest.destination, archive.destination)
    ):
        reasons.append("The file list belongs to another transfer.")
    if rec.id != archive.recording_id:
        reasons.append("The archive copy belongs to another recording.")
    elif (
        rec.archive_state is not ArchiveState.ARCHIVED
        or archive.destination is None
        or not (_same_path(join_location(rec.storage_root, rec.rel_path), archive.destination))
    ):
        reasons.append("The recording no longer points at the archive copy.")
    if archive.destination is not None and _same_path(archive.source, archive.destination):
        reasons.append("The archive copy and the laptop copy are the same folder.")
    for f in manifest.files:
        try:
            safe_rel_path(f.path)
        except ValueError as exc:
            reasons.append(str(exc))
            break
    return reasons


def _is_regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _inside(path: Path, root: Path) -> bool:
    """True when path, with links resolved, lies inside root."""
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:
        return False


def _keep_reason(plan: DeletePlan, f: ManifestFile, src: Path, dst: Path) -> str | None:
    """Why the source file must stay, or None when it may be deleted."""
    if not _is_regular_file(dst) or dst.stat().st_size != f.size:
        return "The NAS copy is missing or has another size."
    if not _is_regular_file(src):
        return "The laptop file is not a regular file."
    if src.stat().st_size != f.size:
        return "The laptop file changed after the copy."
    if not _inside(src, plan.source):
        return "The laptop file lies outside the recording folder."
    return None


def _remove_empty_folders(plan: DeletePlan) -> list[str]:
    """Remove the folders that held listed files, deepest first, if they are empty."""
    folders: set[str] = {""}
    for f in plan.files:
        parts = f.path.split("/")[:-1]
        for n in range(1, len(parts) + 1):
            folders.add("/".join(parts[:n]))
    removed = []
    for rel in sorted(folders, key=lambda r: (-r.count("/") if r else 1, r)):
        folder = plan.source if not rel else local_path(plan.source, rel)
        try:
            if folder.is_symlink() or not folder.is_dir() or any(folder.iterdir()):
                continue
            folder.rmdir()  # refuses a folder that is not empty
        except OSError:
            continue
        removed.append(rel)
    return removed


def delete_source_files(
    plan: DeletePlan,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int], None] | None = None,
) -> DeleteResult:
    """Delete the plan's files from the source folder. See the module text."""
    deleted: list[str] = []
    gone: list[str] = []
    kept: list[KeptFile] = []
    stopped = False
    for done, f in enumerate(plan.files, start=1):
        if cancelled is not None and cancelled():
            stopped = True
            break
        src = local_path(plan.source, f.path)
        dst = local_path(plan.destination, f.path)
        try:
            if not src.exists() and not src.is_symlink():
                gone.append(f.path)
                continue
            reason = _keep_reason(plan, f, src, dst)
            if reason is None:
                src.unlink()
                deleted.append(f.path)
            else:
                kept.append(KeptFile(rel_path=f.path, reason=reason))
        except OSError as exc:
            kept.append(KeptFile(rel_path=f.path, reason=f"Cannot delete the file: {exc}"))
        finally:
            if progress is not None:
                progress(done)
    folders = [] if stopped else _remove_empty_folders(plan)
    return DeleteResult(
        deleted=tuple(deleted),
        already_gone=tuple(gone),
        kept=tuple(kept),
        folders_removed=tuple(folders),
        cancelled=stopped,
    )
