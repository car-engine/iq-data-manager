"""Verification of a copy against its selection (SPEC section 8, "Transfer safety").

verify_copy() always compares each file's presence and size. Depending on the hash
mode it also compares SHA-256 values of source and destination:
- none: no hashes;
- sample: ceil(fraction * n) files, at least one, chosen as the files whose relative
  path has the smallest SHA-256. The choice depends only on the paths, so a second
  check of the same selection hashes the same files;
- all: every file.

Source hashes computed by the copy engine are used where they exist; other source
files are read. Files in the destination's folders that the selection does not list
are reported in `extra` and do not fail the verification.

Note: reading a file straight after writing it to a network share may be served from
the PC's cache. A later "Check archive" reads the files again.
"""

import hashlib
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from iqdm.models import HashMode
from iqdm.transfer.copier import CHUNK_BYTES, CopyItem, local_path


class ProblemKind(StrEnum):
    MISSING = "missing"
    SIZE = "size"
    HASH = "hash"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, kw_only=True)
class FileProblem:
    rel_path: str
    kind: ProblemKind
    message: str


@dataclass(frozen=True, kw_only=True)
class VerifyProgress:
    files_done: int
    files_total: int


@dataclass(frozen=True, kw_only=True)
class VerifyResult:
    """passed is True when every file is present with its size and every hash agrees."""

    passed: bool
    problems: tuple[FileProblem, ...]
    hashes: Mapping[str, str] = field(default_factory=dict)  # files whose hashes agree
    extra: tuple[str, ...] = ()
    cancelled: bool = False


class _Cancelled(Exception):  # noqa: N818  (a request, not an error)
    pass


def _path_key(rel_path: str) -> str:
    return hashlib.sha256(rel_path.encode("utf-8")).hexdigest()


def sample_paths(rel_paths: Iterable[str], fraction: float) -> frozenset[str]:
    """ceil(fraction * n) paths, at least one, with the smallest SHA-256 of the path."""
    paths = sorted(set(rel_paths), key=_path_key)
    if not paths:
        return frozenset()
    if not 0 < fraction <= 1:
        raise ValueError(f"fraction must be above 0 and at most 1, got {fraction}")
    return frozenset(paths[: max(1, math.ceil(fraction * len(paths)))])


def hash_targets(rel_paths: Sequence[str], mode: HashMode, fraction: float) -> frozenset[str]:
    """The paths that verification hashes in this mode."""
    if mode is HashMode.NONE:
        return frozenset()
    if mode is HashMode.ALL:
        return frozenset(rel_paths)
    return sample_paths(rel_paths, fraction)


def file_sha256(
    path: Path,
    *,
    chunk_bytes: int = CHUNK_BYTES,
    cancelled: Callable[[], bool] | None = None,
) -> str:
    """SHA-256 of a file, read in chunks. Raises _Cancelled between chunks."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_bytes):
            if cancelled is not None and cancelled():
                raise _Cancelled
            hasher.update(chunk)
    return hasher.hexdigest()


def _extra_files(destination: Path, items: Sequence[CopyItem]) -> tuple[str, ...]:
    """Files in the folders the selection writes to that it does not list."""
    listed = {i.rel_path for i in items}
    folders = {i.rel_path.rpartition("/")[0] for i in items}
    extra = []
    for folder in sorted(folders):
        path = destination if not folder else local_path(destination, folder)
        if not path.is_dir():
            continue
        for entry in path.iterdir():
            rel = f"{folder}/{entry.name}" if folder else entry.name
            if entry.is_file() and rel not in listed:
                extra.append(rel)
    return tuple(sorted(extra))


def verify_copy(
    source: Path,
    destination: Path,
    items: Sequence[CopyItem],
    *,
    hash_mode: HashMode,
    sample_fraction: float,
    source_hashes: Mapping[str, str] | None = None,
    progress: Callable[[VerifyProgress], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    chunk_bytes: int = CHUNK_BYTES,
) -> VerifyResult:
    """Compare the destination with the selection. See the module text for the rules."""
    known = dict(source_hashes or {})
    targets = hash_targets([i.rel_path for i in items], hash_mode, sample_fraction)
    problems: list[FileProblem] = []
    hashes: dict[str, str] = {}

    def report(done: int) -> None:
        if progress is not None:
            progress(VerifyProgress(files_done=done, files_total=len(items)))

    try:
        for done, item in enumerate(items, start=1):
            if cancelled is not None and cancelled():
                raise _Cancelled
            problem = _check_file(
                source,
                destination,
                item,
                item.rel_path in targets,
                known,
                hashes,
                cancelled,
                chunk_bytes,
            )
            if problem is not None:
                problems.append(problem)
            report(done)
    except _Cancelled:
        return VerifyResult(passed=False, problems=tuple(problems), cancelled=True)
    return VerifyResult(
        passed=not problems,
        problems=tuple(problems),
        hashes=hashes,
        extra=_extra_files(destination, items),
    )


def _check_file(
    source: Path,
    destination: Path,
    item: CopyItem,
    hashed: bool,
    known: Mapping[str, str],
    hashes: dict[str, str],
    cancelled: Callable[[], bool] | None,
    chunk_bytes: int,
) -> FileProblem | None:
    rel = item.rel_path
    dst = local_path(destination, rel)
    if not dst.is_file():
        return FileProblem(
            rel_path=rel, kind=ProblemKind.MISSING, message="Not in the destination."
        )
    size = dst.stat().st_size
    if size != item.size:
        return FileProblem(
            rel_path=rel,
            kind=ProblemKind.SIZE,
            message=f"{size:,} bytes in the destination, {item.size:,} in the source.",
        )
    if not hashed:
        return None
    try:
        src_hash = known.get(rel) or file_sha256(
            local_path(source, rel), chunk_bytes=chunk_bytes, cancelled=cancelled
        )
        dst_hash = file_sha256(dst, chunk_bytes=chunk_bytes, cancelled=cancelled)
    except OSError as exc:
        return FileProblem(
            rel_path=rel, kind=ProblemKind.UNREADABLE, message=f"Cannot read the file: {exc}"
        )
    if src_hash != dst_hash:
        return FileProblem(
            rel_path=rel,
            kind=ProblemKind.HASH,
            message="The content differs from the source (SHA-256).",
        )
    hashes[rel] = dst_hash
    return None
