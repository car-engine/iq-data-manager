"""Recording folder scanner. No GUI imports.

scan_recording() lists the data files of a recording folder per channel, with sizes
and gaps (SPEC section 7, DECISIONS.md D11 and D12). check_channel() compares a
channel's file sizes with its sample rate and format (SPEC section 6, D3).

The scanner only reads directory listings. It opens no files.
"""

import itertools
import math
import os
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import Path

from iqdm.models import BYTES_PER_SAMPLE, SampleType

DEFAULT_EXTENSIONS: tuple[str, ...] = (".dat", ".bin")
GAP_FACTOR = 1.5  # a gap exists where consecutive timestamps differ by more (D12)
CLOSE_FACTOR = 0.5  # files closer than this many durations are an error (D12)
PROGRESS_EVERY = 1000  # data files between progress calls and entries between cancel checks
NAMES_SHOWN = 10  # file names listed in one error message or finding

_STEM_RE = re.compile(r"^\d+(\.\d+)?$", re.ASCII)
_CHANNEL_DIR_RE = re.compile(r"^(0|[1-9]\d*)$", re.ASCII)
_LEADING_ZERO_RE = re.compile(r"^0\d+$", re.ASCII)


class ScanError(Exception):
    """The folder cannot be scanned, or breaks a folder rule in DECISIONS.md D11.

    `problems` lists every problem found, one message each.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


class ScanCancelled(Exception):  # noqa: N818  (a request, not an error)
    """The cancelled() callback returned True during a scan."""


class Severity(StrEnum):
    ERROR = "error"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class DataFile:
    """One data file in a channel folder."""

    name: str
    timestamp: float
    size: int


@dataclass(frozen=True, kw_only=True)
class Gap:
    """A run of missing files. start_unix is the first missing second."""

    start_unix: float
    missing_seconds: float


@dataclass(frozen=True, kw_only=True)
class ChannelScan:
    """The data files of one channel, sorted by timestamp. end_unix is exclusive."""

    channel_index: int
    sub_path: str  # '' when the files sit in the recording folder
    file_duration_s: float
    files: tuple[DataFile, ...]

    @property
    def n_files(self) -> int:
        return len(self.files)

    @property
    def timestamps(self) -> tuple[float, ...]:
        return tuple(f.timestamp for f in self.files)

    @property
    def start_unix(self) -> float | None:
        """First file's timestamp, or None if the channel has no files."""
        return self.files[0].timestamp if self.files else None

    @property
    def end_unix(self) -> float | None:
        """Last file's timestamp + file duration, or None if the channel has no files."""
        return self.files[-1].timestamp + self.file_duration_s if self.files else None

    @property
    def last_file_bytes(self) -> int | None:
        """Size of the last file (D3), or None if the channel has no files."""
        return self.files[-1].size if self.files else None

    @cached_property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)

    @cached_property
    def sizes(self) -> frozenset[int]:
        """Distinct file sizes, including the last file's."""
        return frozenset(f.size for f in self.files)

    @cached_property
    def gaps(self) -> tuple[Gap, ...]:
        """Runs of missing files by the rule in DECISIONS.md D12."""
        dur = self.file_duration_s
        gaps = []
        for a, b in itertools.pairwise(self.files):
            d = b.timestamp - a.timestamp
            if d > GAP_FACTOR * dur:
                n = math.floor(d / dur + 0.5)  # nearest whole number, halves up
                gaps.append(Gap(start_unix=a.timestamp + dur, missing_seconds=(n - 1) * dur))
        return tuple(gaps)


@dataclass(frozen=True, kw_only=True)
class ScanResult:
    """Channels sorted by index, and the entries the scanner did not recognise.

    Unrecognised entries are paths relative to the recording folder, '/'-separated.
    Folders end with '/'.
    """

    root: Path
    file_duration_s: float
    channels: tuple[ChannelScan, ...]
    unrecognised: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One result of check_channel(), for the Log tab's validation checklist."""

    severity: Severity
    channel_index: int
    message: str


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


class _Tracker:
    """Counts entries and data files, reports progress and checks for cancellation."""

    def __init__(
        self,
        progress: Callable[[int], None] | None,
        cancelled: Callable[[], bool] | None,
    ) -> None:
        self._progress = progress
        self._cancelled = cancelled
        self.entries = 0
        self.files = 0

    def check_cancelled(self) -> None:
        if self._cancelled is not None and self._cancelled():
            raise ScanCancelled

    def entry(self) -> None:
        self.entries += 1
        if self.entries % PROGRESS_EVERY == 0:
            self.check_cancelled()

    def data_file(self) -> None:
        self.files += 1
        if self._progress is not None and self.files % PROGRESS_EVERY == 0:
            self._progress(self.files)

    def finish(self) -> None:
        if self._progress is not None:
            self._progress(self.files)


@dataclass
class _Listing:
    """One folder's entries, sorted into data files, subfolders and the rest."""

    files: list[DataFile]
    dirs: list[str]
    unrecognised: list[str]  # names only; folders end with '/'


def _parse_data_name(name: str, extensions: frozenset[str]) -> float | None:
    """The timestamp of a data file name, or None if the name is not one."""
    stem, dot, ext = name.rpartition(".")
    if not dot or f".{ext}".lower() not in extensions or not _STEM_RE.match(stem):
        return None
    return float(stem)


def _list_folder(folder: Path, extensions: frozenset[str], tracker: _Tracker) -> _Listing:
    """List one folder with a single os.scandir call. Sizes come from the entries."""
    listing = _Listing(files=[], dirs=[], unrecognised=[])
    tracker.check_cancelled()
    with os.scandir(folder) as entries:
        for entry in entries:
            tracker.entry()
            if entry.is_symlink() or entry.is_junction():
                listing.unrecognised.append(entry.name)
            elif entry.is_dir(follow_symlinks=False):
                listing.dirs.append(entry.name)
            elif entry.is_file(follow_symlinks=False):
                t = _parse_data_name(entry.name, extensions)
                if t is None:
                    listing.unrecognised.append(entry.name)
                else:
                    size = entry.stat(follow_symlinks=False).st_size
                    listing.files.append(DataFile(name=entry.name, timestamp=t, size=size))
                    tracker.data_file()
            else:
                listing.unrecognised.append(entry.name)
    return listing


def _names(names: Iterable[str]) -> str:
    """'a, b, c' with at most NAMES_SHOWN names, then 'and N more'."""
    names = list(names)
    shown = ", ".join(names[:NAMES_SHOWN])
    rest = len(names) - NAMES_SHOWN
    return f"{shown} and {rest} more" if rest > 0 else shown


def _channel_label(index: int, sub_path: str) -> str:
    where = f"folder {sub_path}" if sub_path else "recording folder"
    return f"channel {index} ({where})"


def _make_channel(
    index: int, sub_path: str, file_duration_s: float, files: list[DataFile]
) -> tuple[ChannelScan, list[str]]:
    """Sort a channel's files. Returns the channel and its duplicate-timestamp problems."""
    files.sort(key=lambda f: (f.timestamp, f.name))
    dupes = [
        f"{a.name} and {b.name}" for a, b in itertools.pairwise(files) if a.timestamp == b.timestamp
    ]
    problems = []
    if dupes:
        problems.append(
            f"{_channel_label(index, sub_path)}: {len(dupes)} timestamps appear twice: "
            f"{_names(dupes)}"
        )
    channel = ChannelScan(
        channel_index=index,
        sub_path=sub_path,
        file_duration_s=file_duration_s,
        files=tuple(files),
    )
    return channel, problems


def _normalise_extensions(extensions: Iterable[str]) -> frozenset[str]:
    exts = frozenset(e.lower() for e in extensions)
    if not exts or any(not e.startswith(".") or len(e) < 2 for e in exts):
        raise ValueError(f"extensions must be like '.dat', got {sorted(exts)}")
    return exts


def scan_recording(
    folder: Path,
    file_duration_s: float,
    *,
    extensions: Iterable[str] = DEFAULT_EXTENSIONS,
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ScanResult:
    """Scan a recording folder by the rules in SPEC section 7.

    progress(files_seen) is called every PROGRESS_EVERY data files and once at the end
    with the total. cancelled() is checked at every folder and every PROGRESS_EVERY
    entries; when it returns True the scan raises ScanCancelled.

    Raises ScanError if the folder is missing or breaks a rule in DECISIONS.md D11,
    and ValueError for a non-positive file duration or a malformed extension.
    """
    if not math.isfinite(file_duration_s) or file_duration_s <= 0:
        raise ValueError(f"file_duration_s must be positive, got {file_duration_s}")
    exts = _normalise_extensions(extensions)
    root = Path(folder)
    if not root.exists():
        raise ScanError([f"folder not found: {root}"])
    if not root.is_dir():
        raise ScanError([f"not a folder: {root}"])

    tracker = _Tracker(progress, cancelled)
    try:
        top = _list_folder(root, exts, tracker)
    except OSError as exc:
        raise ScanError([f"cannot list {root}: {exc}"]) from exc

    problems: list[str] = []
    unrecognised = list(top.unrecognised)
    channel_dirs: list[str] = []
    for name in top.dirs:
        if _CHANNEL_DIR_RE.match(name):
            channel_dirs.append(name)
        elif _LEADING_ZERO_RE.match(name):
            problems.append(f"channel folder name has a leading zero: {name}")
        else:
            unrecognised.append(f"{name}/")
    channel_dirs.sort(key=int)

    channels: list[ChannelScan] = []
    if channel_dirs:
        if top.files:
            names = sorted(f.name for f in top.files)
            problems.append(
                f"{len(names)} data files sit in the recording folder next to channel "
                f"folders: {_names(names)}"
            )
        for name in channel_dirs:
            try:
                listing = _list_folder(root / name, exts, tracker)
            except OSError as exc:
                problems.append(f"cannot list folder {name}: {exc}")
                continue
            unrecognised += [f"{name}/{n}" for n in listing.unrecognised]
            unrecognised += [f"{name}/{d}/" for d in listing.dirs]
            channel, dupes = _make_channel(int(name), name, file_duration_s, listing.files)
            channels.append(channel)
            problems += dupes
    elif top.files:
        channel, dupes = _make_channel(0, "", file_duration_s, top.files)
        channels.append(channel)
        problems += dupes

    if problems:
        raise ScanError(problems)
    tracker.finish()
    return ScanResult(
        root=root,
        file_duration_s=file_duration_s,
        channels=tuple(channels),
        unrecognised=tuple(sorted(unrecognised)),
    )


# ---------------------------------------------------------------------------
# Channel check
# ---------------------------------------------------------------------------


def expected_file_bytes(
    fs_hz: float, file_duration_s: float, dtype: SampleType | str, header_bytes: int
) -> int:
    """header_bytes + fs_hz * file_duration_s * 2 * bytes per sample (SPEC section 6).

    Raises ValueError unless fs_hz * file_duration_s is a positive whole number of
    samples and header_bytes is >= 0.
    """
    if header_bytes < 0:
        raise ValueError(f"header_bytes must be >= 0, got {header_bytes}")
    samples = fs_hz * file_duration_s
    n = round(samples) if math.isfinite(samples) else 0
    if n <= 0 or abs(samples - n) > 1e-9 * samples:
        raise ValueError(
            f"fs * file duration must be a positive whole number of samples, got {samples:g}"
        )
    return header_bytes + n * 2 * BYTES_PER_SAMPLE[SampleType(dtype)]


def _size_findings(
    channel: ChannelScan, label: str, expected: int, header_bytes: int
) -> list[Finding]:
    files = channel.files
    last = len(files) - 1
    wrong: list[DataFile] = []
    findings: list[Finding] = []
    for i, f in enumerate(files):
        if f.size == expected:
            continue
        # A short last file is information (D3) only if it holds IQ data (D13).
        if i == last and i > 0 and header_bytes < f.size < expected:
            findings.append(
                Finding(
                    severity=Severity.INFO,
                    channel_index=channel.channel_index,
                    message=(
                        f"{label}: the last file {f.name} is {f.size} bytes, shorter than "
                        f"the expected {expected} bytes"
                    ),
                )
            )
        else:
            wrong.append(f)
    if wrong:
        findings.insert(
            0,
            Finding(
                severity=Severity.ERROR,
                channel_index=channel.channel_index,
                message=(
                    f"{label}: {len(wrong)} files differ from the expected size of "
                    f"{expected} bytes: {_names(f'{f.name} ({f.size} bytes)' for f in wrong)}"
                ),
            ),
        )
    return findings


def _spacing_findings(channel: ChannelScan, label: str) -> list[Finding]:
    dur = channel.file_duration_s
    close = [
        f"{a.name} and {b.name}"
        for a, b in itertools.pairwise(channel.files)
        if b.timestamp - a.timestamp < CLOSE_FACTOR * dur
    ]
    if not close:
        return []
    return [
        Finding(
            severity=Severity.ERROR,
            channel_index=channel.channel_index,
            message=(
                f"{label}: {len(close)} pairs of files are closer together than half the "
                f"file duration of {dur:g} s: {_names(close)}. Check the file duration."
            ),
        )
    ]


def check_channel(
    channel: ChannelScan, *, fs_hz: float, dtype: SampleType | str, header_bytes: int
) -> list[Finding]:
    """Check a scanned channel against its sample rate and file format.

    Errors: no data files; fs * duration not a whole number of samples; any file of
    the wrong size, except a short last file; files closer together than half the
    file duration. Information: a short last file (DECISIONS.md D3). A channel with
    one file has no last file in this sense, so a short single file is an error (D11).
    A last file of header_bytes bytes or fewer holds no IQ data and is an error (D13).
    """
    label = _channel_label(channel.channel_index, channel.sub_path)
    if not channel.files:
        return [
            Finding(
                severity=Severity.ERROR,
                channel_index=channel.channel_index,
                message=f"{label} has no data files",
            )
        ]
    findings: list[Finding] = []
    try:
        expected = expected_file_bytes(fs_hz, channel.file_duration_s, dtype, header_bytes)
    except ValueError as exc:
        findings.append(
            Finding(
                severity=Severity.ERROR,
                channel_index=channel.channel_index,
                message=f"{label}: {exc}",
            )
        )
    else:
        findings += _size_findings(channel, label, expected, header_bytes)
    findings += _spacing_findings(channel, label)
    return findings
