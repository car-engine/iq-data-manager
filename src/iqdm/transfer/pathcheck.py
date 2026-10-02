"""Destination checks before a transfer (SPEC section 8, "Transfer safety").

check_destination() returns every problem it finds as a message for the user, and the
target files that already exist with the right size (resume, DECISIONS.md D51).

Path text is compared as Windows paths with PureWindowsPath, which ignores letter
case and compares whole components, as location.py does. A mapped drive letter is
replaced by its UNC path first, so a drive path and a UNC path to the same folder
compare equal.
"""

import ntpath
import os
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import NamedTuple

from iqdm.entry import format_size
from iqdm.location import DriveResolver, LocationError, mapped_drive_unc, split_location
from iqdm.models import ArchiveState, Operation
from iqdm.transfer.selection import Selection

PARTIAL_SUFFIX = ".partial"  # the copy engine writes here first (D48)
MAX_FILE_PATH = 259  # Windows MAX_PATH less the terminating null
MAX_FOLDER_PATH = 247  # CreateDirectory leaves room for an 8.3 file name
NAMES_SHOWN = 10  # file names listed in one message
GB = 1_000_000_000


class DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


DiskUsageFn = Callable[[str | Path], DiskUsage]


@dataclass(frozen=True, kw_only=True)
class DestinationCheck:
    """The result of check_destination().

    errors block the transfer. notes are information for the preview. existing holds
    the target files already in place with their source size; the copy skips them.
    """

    destination: Path
    errors: tuple[str, ...]
    notes: tuple[str, ...]
    existing: frozenset[str]
    bytes_to_copy: int

    @property
    def ok(self) -> bool:
        return not self.errors


def long_paths_enabled() -> bool:
    """True when Windows allows paths above MAX_PATH, or off Windows.

    Reads LongPathsEnabled under HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem.
    The packaged app also needs a manifest that declares longPathAware (O33).
    """
    if sys.platform != "win32":
        return True
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
    except OSError:
        return False
    return value == 1


def windows_path(text: str | Path, resolve_drive: DriveResolver | None) -> PureWindowsPath:
    """Normalised absolute Windows path, with a mapped drive replaced by its UNC path.

    Raises ValueError for a relative path.
    """
    path = PureWindowsPath(ntpath.normpath(str(text)))
    if not path.drive or not path.root:
        raise ValueError(f"not a full path: {text}")
    if resolve_drive is not None and len(path.drive) == 2 and path.drive[1] == ":":
        unc = resolve_drive(path.drive.upper())
        if unc:
            path = PureWindowsPath(ntpath.normpath(unc), *path.parts[1:])
    return path


def files_text(n: int) -> str:
    """'1 file', '2 files', '1,200 files'."""
    return "1 file" if n == 1 else f"{n:,} files"


def _names(names: Sequence[str]) -> str:
    shown = ", ".join(names[:NAMES_SHOWN])
    more = f", and {len(names) - NAMES_SHOWN:,} more" if len(names) > NAMES_SHOWN else ""
    return shown + more


def _path_errors(source: PureWindowsPath, dest: PureWindowsPath, dest_text: str) -> list[str]:
    if len(dest.parts) < 2:
        return [
            f"The destination {dest_text} is a drive or a network share itself. "
            "Choose a folder in it."
        ]
    if dest == source:
        return ["The destination is the source folder. Choose another folder."]
    if dest.is_relative_to(source):
        return ["The destination is inside the source folder. Choose a folder outside it."]
    if source.is_relative_to(dest):
        return ["The source folder is inside the destination. Choose a new folder for the copy."]
    return []


def _archive_errors(
    dest_text: str, nas_roots: Sequence[str], resolve_drive: DriveResolver | None
) -> list[str]:
    """An archive destination lies under a NAS location (D50)."""
    try:
        location = split_location(dest_text, nas_roots, resolve_drive)
    except LocationError as exc:
        return [f"The destination cannot hold a recording: {exc}."]
    if location.archive_state is not ArchiveState.ARCHIVED:
        return [
            "An archive goes to a folder in one of the NAS locations in Settings. "
            f"{dest_text} is not in one."
        ]
    return []


class _Listing(NamedTuple):
    files: dict[str, int]  # '/'-separated relative path -> size
    folders: set[str]  # '/'-separated relative paths
    links: list[str]


def _list_destination(dest: Path) -> _Listing:
    files: dict[str, int] = {}
    folders: set[str] = set()
    links: list[str] = []
    for dirpath, dirnames, filenames in os.walk(dest):
        base = Path(dirpath).relative_to(dest).as_posix()
        prefix = "" if base == "." else base + "/"
        for name in list(dirnames):
            full = Path(dirpath) / name
            if full.is_symlink():
                links.append(prefix + name)
                dirnames.remove(name)
            else:
                folders.add(prefix + name)
        for name in filenames:
            full = Path(dirpath) / name
            if full.is_symlink():
                links.append(prefix + name)
            else:
                files[prefix + name] = full.stat().st_size
    return _Listing(files, folders, links)


def _nearest_existing(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return path


def _length_errors(dest: PureWindowsPath, selection: Selection) -> list[str]:
    errors = []
    longest_file = max((str(dest / f.rel_path) + PARTIAL_SUFFIX for f in selection.files), key=len)
    if len(longest_file) > MAX_FILE_PATH:
        errors.append(
            f"File paths in the destination would be {len(longest_file)} characters long. "
            f"Windows allows {MAX_FILE_PATH}. Choose a shorter destination path."
        )
    folders = [str(dest / c.sub_path) for c in selection.channels]
    longest_folder = max(folders, key=len)
    if len(longest_folder) > MAX_FOLDER_PATH:
        errors.append(
            f"Folder paths in the destination would be {len(longest_folder)} characters "
            f"long. Windows allows {MAX_FOLDER_PATH}. Choose a shorter destination path."
        )
    return errors


def check_destination(
    selection: Selection,
    destination: str | Path,
    *,
    operation: Operation,
    margin_bytes: int,
    nas_roots: Sequence[str] = (),
    resolve_drive: DriveResolver | None = mapped_drive_unc,
    disk_usage: DiskUsageFn = shutil.disk_usage,
    long_paths: bool | None = None,
) -> DestinationCheck:
    """Check a destination folder for a copy or a move of `selection`.

    A move needs a destination that is new, is empty, or holds only target files,
    their .partial files and their channel folders. A copy also accepts other files.
    A target file with another size than its source is an error in both (D51).
    A move must go to a folder under a NAS root (D50). long_paths None reads the
    Windows setting.
    """
    if operation not in (Operation.COPY, Operation.MOVE):
        raise ValueError(f"only a copy or a move has a destination, got {operation}")
    dest = Path(destination)
    dest_text = str(destination)
    errors: list[str] = []
    notes: list[str] = []
    try:
        dest_win = windows_path(destination, resolve_drive)
        source_win = windows_path(selection.source, resolve_drive)
    except ValueError:
        return DestinationCheck(
            destination=dest,
            errors=(f"The destination {dest_text} is not a full path.",),
            notes=(),
            existing=frozenset(),
            bytes_to_copy=selection.total_bytes,
        )
    errors += _path_errors(source_win, dest_win, dest_text)
    if operation is Operation.MOVE:
        errors += _archive_errors(dest_text, nas_roots, resolve_drive)

    targets = {f.rel_path: f.size for f in selection.files}
    existing: set[str] = set()
    if errors:
        pass  # do not look inside a destination that overlaps the source
    elif dest.exists() and not dest.is_dir():
        errors.append(f"The destination {dest_text} is a file. Choose a folder.")
    elif dest.is_dir():
        try:
            listing = _list_destination(dest)
        except OSError as exc:
            errors.append(f"Cannot read the destination folder: {exc}")
        else:
            errors += _content_errors(listing, targets, selection, operation, existing, notes)

    bytes_to_copy = sum(size for rel, size in targets.items() if rel not in existing)
    if not errors:
        errors += _space_errors(dest, bytes_to_copy, margin_bytes, disk_usage)
        enabled = long_paths_enabled() if long_paths is None else long_paths
        if not enabled:
            errors += _length_errors(dest_win, selection)
    return DestinationCheck(
        destination=dest,
        errors=tuple(errors),
        notes=tuple(notes),
        existing=frozenset(existing),
        bytes_to_copy=bytes_to_copy,
    )


def _content_errors(
    listing: _Listing,
    targets: dict[str, int],
    selection: Selection,
    operation: Operation,
    existing: set[str],
    notes: list[str],
) -> list[str]:
    """Compare the destination's files with the targets. Fills `existing` and `notes`."""
    errors = []
    wrong = []
    for rel, size in sorted(listing.files.items()):
        if rel in targets:
            if size == targets[rel]:
                existing.add(rel)
            else:
                wrong.append(rel)
    if wrong:
        errors.append(
            f"Files in the destination have the same name as a file to copy and another "
            f"size ({files_text(len(wrong))}): {_names(wrong)}. The copy never replaces a "
            "file. Choose another folder."
        )
    partials = {rel + PARTIAL_SUFFIX for rel in targets}
    channel_folders = {c.sub_path for c in selection.channels if c.sub_path}
    other_files = sorted(set(listing.files) - set(targets) - partials)
    other_folders = sorted(listing.folders - channel_folders)
    if listing.links:
        errors.append(f"The destination holds links: {_names(sorted(listing.links))}.")
    if operation is Operation.MOVE and (other_files or other_folders):
        errors.append(
            "An archive needs a new or empty folder. The destination holds other files "
            f"or folders: {_names(other_folders + other_files)}."
        )
    elif other_files:
        notes.append(f"The destination already holds other files ({files_text(len(other_files))}).")
    if existing and not errors:
        notes.append(
            f"Already in the destination with the right size: {files_text(len(existing))}. "
            "They are not copied again and are checked with the rest."
        )
    return errors


def _space_errors(
    dest: Path, bytes_to_copy: int, margin_bytes: int, disk_usage: DiskUsageFn
) -> list[str]:
    try:
        free = disk_usage(_nearest_existing(dest)).free
    except OSError as exc:
        return [f"Cannot read the free space at the destination: {exc}"]
    if free < bytes_to_copy + margin_bytes:
        return [
            f"Not enough free space at the destination: the copy needs "
            f"{format_size(bytes_to_copy)} and keeps {format_size(margin_bytes)} free, "
            f"and {format_size(free)} is free."
        ]
    return []
