"""The copy engine: copies selected files into a destination folder (DECISIONS.md D48).

Rules (SPEC section 8, "Copy engine"):
- Each file is written in chunks to <name>.partial, flushed to disk, given the
  source's modification time, and renamed to its real name only when complete. The
  rename never replaces an existing file, so a file under its real name is always
  complete. On Windows Path.rename() refuses an existing target; the engine also
  checks for one first, because other systems would replace it.
- The flush (os.fsync, FlushFileBuffers on Windows) waits until the destination has
  the data on its disks, so a crash there cannot leave a file with its real name but
  without its data. fsync=False skips it, for timing comparisons only (D54).
- A target that already exists with the source's size counts as copied (resume,
  D51). A target with another size is a failure, and the engine leaves it alone.
- A source file whose size or modification time changes during the copy is a
  failure.
- Each file gets up to `retries` further attempts after an OSError, `retry_pause_s`
  apart.
- cancelled() is checked between chunks and between files. Cancel leaves the
  .partial file, which a later run overwrites.

The engine deletes nothing. It writes only inside the destination folder, under
relative paths that manifest.safe_rel_path() accepts.
"""

import hashlib
import os
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from iqdm.transfer.manifest import safe_rel_path
from iqdm.transfer.pathcheck import PARTIAL_SUFFIX

CHUNK_BYTES = 8 * 1024 * 1024
RETRIES = 3  # further attempts after the first, as robocopy /R:3
RETRY_PAUSE_S = 5.0  # as robocopy /W:5
PAUSE_STEP_S = 0.25  # a cancel during a retry pause takes effect within this time

SourceOpener = Callable[[Path], BinaryIO]


@dataclass(frozen=True, kw_only=True)
class RetryNotice:
    """A file failed an attempt and is tried again after a pause."""

    rel_path: str
    attempt: int  # the attempt that comes next, from 2
    attempts: int  # all attempts, retries plus the first
    pause_s: float
    message: str


@dataclass(frozen=True, kw_only=True)
class CopyItem:
    """One file to copy. size is the source size from the selection's scan."""

    rel_path: str  # '/'-separated, relative to the source and destination folders
    size: int


@dataclass(frozen=True, kw_only=True)
class CopyProgress:
    files_done: int  # copied, skipped and failed files
    files_total: int
    bytes_done: int  # bytes written, plus the size of skipped files
    bytes_total: int


@dataclass(frozen=True, kw_only=True)
class FileFailure:
    rel_path: str
    message: str


@dataclass(frozen=True, kw_only=True)
class CopyResult:
    """What happened to each file. Files neither copied, skipped nor failed were not
    reached before a cancel."""

    copied: tuple[str, ...]
    skipped: tuple[str, ...]  # already in place with the right size
    failed: tuple[FileFailure, ...]
    cancelled: bool
    bytes_copied: int
    source_hashes: Mapping[str, str] = field(default_factory=dict)  # copied files only

    @property
    def ok(self) -> bool:
        return not self.failed and not self.cancelled


class _Cancelled(Exception):  # noqa: N818  (a request, not an error)
    pass


class _Failed(Exception):  # noqa: N818  (carries a failure that is not retried)
    pass


def local_path(root: Path, rel_path: str) -> Path:
    """root joined with a '/'-separated relative path that stays inside it."""
    return root.joinpath(*safe_rel_path(rel_path).split("/"))


def partial_path(target: Path) -> Path:
    return target.with_name(target.name + PARTIAL_SUFFIX)


def _open_source(path: Path) -> BinaryIO:
    return path.open("rb")


class _Progress:
    """Counts shared between worker threads. Reports under a lock, in order."""

    def __init__(
        self, items: Sequence[CopyItem], callback: Callable[[CopyProgress], None] | None
    ) -> None:
        self._lock = threading.Lock()
        self._callback = callback
        self.files_total = len(items)
        self.bytes_total = sum(i.size for i in items)
        self.files_done = 0
        self.bytes_done = 0

    def add(self, *, files: int = 0, n_bytes: int = 0) -> None:
        with self._lock:
            self.files_done += files
            self.bytes_done += n_bytes
            if self._callback is not None:
                self._callback(
                    CopyProgress(
                        files_done=self.files_done,
                        files_total=self.files_total,
                        bytes_done=self.bytes_done,
                        bytes_total=self.bytes_total,
                    )
                )


@dataclass
class _Engine:
    source: Path
    destination: Path
    hash_source: bool
    fsync: bool
    retries: int
    retry_pause_s: float
    sleep: Callable[[float], None]
    chunk_bytes: int
    open_source: SourceOpener
    cancelled: Callable[[], bool]
    progress: _Progress
    retrying: Callable[[RetryNotice], None] | None = None

    def copy(self, item: CopyItem) -> tuple[str, str | None]:
        """Copy one file. Returns ('copied', hash) or ('skipped', None).

        Raises _Failed with a message, or _Cancelled.
        """
        src = local_path(self.source, item.rel_path)
        dst = local_path(self.destination, item.rel_path)
        if os.path.lexists(dst):
            if dst.is_file() and not dst.is_symlink() and dst.stat().st_size == item.size:
                self.progress.add(files=1, n_bytes=item.size)
                return "skipped", None
            raise _Failed("A different file with this name is already in the destination.")
        last: OSError | None = None
        for attempt in range(self.retries + 1):
            if self.cancelled():
                raise _Cancelled
            written = 0

            def counted(n: int) -> None:
                nonlocal written
                written += n
                self.progress.add(n_bytes=n)

            try:
                digest = self._attempt(item, src, dst, counted)
            except OSError as exc:
                self.progress.add(n_bytes=-written)
                last = exc
                if attempt < self.retries:
                    if self.retrying is not None:
                        self.retrying(
                            RetryNotice(
                                rel_path=item.rel_path,
                                attempt=attempt + 2,
                                attempts=self.retries + 1,
                                pause_s=self.retry_pause_s,
                                message=str(exc),
                            )
                        )
                    self._pause()
                continue
            except (_Failed, _Cancelled):
                self.progress.add(n_bytes=-written)
                raise
            self.progress.add(files=1)
            return "copied", digest
        raise _Failed(f"Copy failed after {self.retries + 1} attempts: {last}")

    def _pause(self) -> None:
        """Wait retry_pause_s in short steps, so a cancel ends the wait."""
        remaining = self.retry_pause_s
        while remaining > 0 and not self.cancelled():
            step = min(PAUSE_STEP_S, remaining)
            self.sleep(step)
            remaining -= step

    def _attempt(
        self, item: CopyItem, src: Path, dst: Path, counted: Callable[[int], None]
    ) -> str | None:
        before = src.stat()
        if before.st_size != item.size:
            raise _Failed(
                f"The source file is {before.st_size:,} bytes; the scan found {item.size:,}. "
                "Scan the recording again."
            )
        dst.parent.mkdir(parents=True, exist_ok=True)
        partial = partial_path(dst)
        hasher = hashlib.sha256() if self.hash_source else None
        written = 0
        with self.open_source(src) as fin, partial.open("wb") as fout:
            while chunk := fin.read(self.chunk_bytes):
                if self.cancelled():
                    raise _Cancelled
                fout.write(chunk)
                if hasher is not None:
                    hasher.update(chunk)
                written += len(chunk)
                counted(len(chunk))
            fout.flush()  # Python's buffer to the operating system
            if self.fsync:
                os.fsync(fout.fileno())  # the operating system's cache to the disks
        after = src.stat()
        if written != item.size or (after.st_size, after.st_mtime_ns) != (
            before.st_size,
            before.st_mtime_ns,
        ):
            raise _Failed("The source file changed during the copy. Scan the recording again.")
        os.utime(partial, ns=(before.st_atime_ns, before.st_mtime_ns))
        if os.path.lexists(dst):
            raise _Failed("A file with this name appeared in the destination during the copy.")
        partial.rename(dst)  # Windows refuses an existing target
        return None if hasher is None else hasher.hexdigest()


def copy_files(
    source: Path,
    destination: Path,
    items: Sequence[CopyItem],
    *,
    hash_source: bool = False,
    workers: int = 1,
    fsync: bool = True,
    progress: Callable[[CopyProgress], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    retrying: Callable[[RetryNotice], None] | None = None,
    retries: int = RETRIES,
    retry_pause_s: float = RETRY_PAUSE_S,
    sleep: Callable[[float], None] = time.sleep,
    chunk_bytes: int = CHUNK_BYTES,
    open_source: SourceOpener = _open_source,
) -> CopyResult:
    """Copy `items` from `source` to `destination`, `workers` files at a time.

    progress and retrying are called from the worker threads; retrying before each
    pause between attempts. With hash_source, the SHA-256 of each
    copied file is computed from the bytes read and returned in source_hashes.
    fsync=False skips the flush to the destination's disks; it exists for timing
    comparisons (D54), and the app keeps the default.
    """
    if workers < 1:
        raise ValueError(f"workers must be at least 1, got {workers}")
    for item in items:
        safe_rel_path(item.rel_path)
    stop = threading.Event()

    def is_cancelled() -> bool:
        if not stop.is_set() and cancelled is not None and cancelled():
            stop.set()
        return stop.is_set()

    engine = _Engine(
        source=source,
        destination=destination,
        hash_source=hash_source,
        fsync=fsync,
        retries=retries,
        retry_pause_s=retry_pause_s,
        sleep=sleep,
        chunk_bytes=chunk_bytes,
        open_source=open_source,
        cancelled=is_cancelled,
        progress=_Progress(items, progress),
        retrying=retrying,
    )
    outcomes: list[tuple[str, str | None] | FileFailure | None] = [None] * len(items)

    def run(index: int) -> None:
        item = items[index]
        if is_cancelled():
            return
        try:
            outcomes[index] = engine.copy(item)
        except _Cancelled:
            return
        except _Failed as exc:
            outcomes[index] = FileFailure(rel_path=item.rel_path, message=str(exc))
            engine.progress.add(files=1)

    if workers == 1:
        for i in range(len(items)):
            run(i)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(run, range(len(items))))

    copied, skipped, failed, hashes = [], [], [], {}
    copied_bytes = 0
    for item, outcome in zip(items, outcomes, strict=True):
        if isinstance(outcome, FileFailure):
            failed.append(outcome)
        elif outcome is not None:
            kind, digest = outcome
            if kind == "skipped":
                skipped.append(item.rel_path)
            else:
                copied.append(item.rel_path)
                copied_bytes += item.size
                if digest is not None:
                    hashes[item.rel_path] = digest
    return CopyResult(
        copied=tuple(copied),
        skipped=tuple(skipped),
        failed=tuple(failed),
        cancelled=stop.is_set(),
        bytes_copied=copied_bytes,
        source_hashes=hashes,
    )
