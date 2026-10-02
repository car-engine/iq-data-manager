"""Where a recording folder sits: storage_root, rel_path and archive state.

Rules in DECISIONS.md D14. Paths are handled as Windows paths with PureWindowsPath and
ntpath, so split_location() and its tests run on any OS and touch no file. Only
mapped_drive_unc() calls Windows.
"""

import ntpath
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import PureWindowsPath

from iqdm.models import ArchiveState

DriveResolver = Callable[[str], str | None]
"""Maps a drive such as 'Z:' to its UNC path, or None if it is not a network drive."""

_DRIVE_RE = re.compile(r"^[A-Za-z]:$")
_NO_ERROR = 0
_ERROR_MORE_DATA = 234
_ERROR_CONNECTION_UNAVAIL = 1201  # a remembered mapping that is not connected now


class LocationError(ValueError):
    """The folder cannot be logged as a recording folder."""


@dataclass(frozen=True, kw_only=True)
class Location:
    """A recording folder split by DECISIONS.md D14.

    outside_nas_roots is True for a folder on a network share that no configured NAS
    root covers. Such a folder is logged as local.
    """

    storage_root: str
    rel_path: str
    archive_state: ArchiveState
    outside_nas_roots: bool = False

    @property
    def full_path(self) -> str:
        return join_location(self.storage_root, self.rel_path)


def join_location(storage_root: str, rel_path: str) -> str:
    """storage_root and rel_path joined with a backslash."""
    return str(PureWindowsPath(storage_root, rel_path))


def _text(path: PureWindowsPath) -> str:
    """Path text without a trailing separator, except for a drive root such as 'E:\\'."""
    text = str(path)
    if path.drive.startswith("\\\\"):
        return text.rstrip("\\")
    return text


def _is_unc(path: PureWindowsPath) -> bool:
    return path.drive.startswith("\\\\")


def _absolute(text: str) -> PureWindowsPath:
    """Normalised absolute path. Raises LocationError for a relative path."""
    if not text.strip():
        raise LocationError("no folder given")
    path = PureWindowsPath(ntpath.normpath(text.strip()))
    if not path.drive or not path.root:
        raise LocationError(f"not an absolute path: {text}")
    if path.drive.startswith(("\\\\?", "\\\\.")):
        raise LocationError(f"device paths are not supported: {text}")
    return path


def _resolve_mapped_drive(
    path: PureWindowsPath, resolve_drive: DriveResolver | None
) -> PureWindowsPath:
    if resolve_drive is None or not _DRIVE_RE.match(path.drive):
        return path
    unc = resolve_drive(path.drive.upper())
    if not unc:
        return path
    return PureWindowsPath(ntpath.normpath(unc), *path.parts[1:])


def _nas_root_for(path: PureWindowsPath, nas_roots: Sequence[str]) -> PureWindowsPath | None:
    """The longest NAS root that holds the path, or None.

    PureWindowsPath compares whole components and ignores letter case.
    """
    matches = [
        root_path
        for root_path in (PureWindowsPath(ntpath.normpath(r)) for r in nas_roots)
        if path.is_relative_to(root_path)
    ]
    return max(matches, key=lambda r: len(r.parts), default=None)


def split_location(
    folder: str,
    nas_roots: Sequence[str] = (),
    resolve_drive: DriveResolver | None = None,
) -> Location:
    """Split a recording folder into storage_root and rel_path (DECISIONS.md D14).

    A mapped drive letter is first replaced through resolve_drive. Under a NAS root,
    storage_root is that root as configured and the state is archived. Elsewhere,
    storage_root is the parent folder and the state is local.

    Raises LocationError for a relative path, a drive root, a share root or a NAS
    root itself.
    """
    path = _resolve_mapped_drive(_absolute(folder), resolve_drive)
    if len(path.parts) < 2:
        raise LocationError(f"a drive or share root cannot be a recording folder: {_text(path)}")

    root = _nas_root_for(path, nas_roots)
    if root is not None:
        rel = path.relative_to(root)
        if not rel.parts:
            raise LocationError(f"a NAS root cannot be a recording folder: {_text(path)}")
        return Location(
            storage_root=_text(root),
            rel_path=str(rel),
            archive_state=ArchiveState.ARCHIVED,
        )
    return Location(
        storage_root=_text(path.parent),
        rel_path=path.name,
        archive_state=ArchiveState.LOCAL,
        outside_nas_roots=_is_unc(path),
    )


def mapped_drive_unc(drive: str) -> str | None:
    """UNC path of a mapped network drive such as 'Z:', or None.

    Calls WNetGetConnectionW, which reads the local drive mapping and opens no
    folder. Returns None on other operating systems, for a drive that is not a
    network drive, and on any other error.
    """
    if not _DRIVE_RE.match(drive):
        raise ValueError(f"expected a drive such as 'Z:', got {drive!r}")
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    mpr = ctypes.WinDLL("mpr")
    func = mpr.WNetGetConnectionW
    func.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    func.restype = wintypes.DWORD
    size = wintypes.DWORD(260)
    for _ in range(2):
        buffer = ctypes.create_unicode_buffer(size.value)
        result = func(drive, buffer, ctypes.byref(size))
        if result in (_NO_ERROR, _ERROR_CONNECTION_UNAVAIL):
            return buffer.value or None
        if result != _ERROR_MORE_DATA:
            return None
    return None
