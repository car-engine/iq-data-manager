"""Which files a transfer covers: a rescan of the source, a time range and channels.

SPEC section 8, "Selection". The source folder is rescanned before every transfer, so
the selection has the real file names and sizes (DECISIONS.md D53). A file at time t
is in the range when start <= t < end (D49). The missing seconds of a range are the
gap seconds inside it; time before a channel's first file or after its last file is
not missing.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from iqdm.models import Recording
from iqdm.scan.scanner import ChannelScan, Gap, ScanResult, scan_recording
from iqdm.viewer import recording_folder, scan_differences


class SelectionError(ValueError):
    """The channels or the range do not select any file, or name a channel that is absent."""


@dataclass(frozen=True, kw_only=True)
class SelectedFile:
    """One source file. rel_path is relative to the recording folder, '/'-separated."""

    rel_path: str
    size: int
    timestamp: float


@dataclass(frozen=True, kw_only=True)
class ChannelSelection:
    """The selected files of one channel, and the gaps inside the range."""

    channel_index: int
    sub_path: str  # '' when the files sit in the recording folder
    files: tuple[SelectedFile, ...]
    gaps: tuple[Gap, ...]  # clipped to the range

    @property
    def n_files(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def missing_seconds(self) -> float:
        return sum(g.missing_seconds for g in self.gaps)


@dataclass(frozen=True, kw_only=True)
class Selection:
    """What a transfer copies from one recording.

    channel_indices is None when every channel of the recording is selected, as
    transfer_log.channels stores it (D5). differences lists where the folder differs
    from the database entry.
    """

    recording_id: int | None
    source: Path
    file_duration_s: float
    range_start_unix: float | None
    range_end_unix: float | None
    channel_indices: tuple[int, ...] | None
    channels: tuple[ChannelSelection, ...]
    differences: tuple[str, ...]
    scan: ScanResult | None = field(default=None, compare=False, repr=False)  # the rescan

    @property
    def files(self) -> tuple[SelectedFile, ...]:
        return tuple(f for c in self.channels for f in c.files)

    @property
    def n_files(self) -> int:
        return sum(c.n_files for c in self.channels)

    @property
    def total_bytes(self) -> int:
        return sum(c.total_bytes for c in self.channels)

    @property
    def is_whole(self) -> bool:
        """True for the whole recording with all channels (D50)."""
        return (
            self.range_start_unix is None
            and self.range_end_unix is None
            and self.channel_indices is None
        )


def rel_path(sub_path: str, name: str) -> str:
    return f"{sub_path}/{name}" if sub_path else name


def in_range(t: float, start: float | None, end: float | None) -> bool:
    """start <= t < end; a bound of None is open (D49)."""
    return (start is None or start <= t) and (end is None or t < end)


def clip_gaps(gaps: Iterable[Gap], start: float | None, end: float | None) -> tuple[Gap, ...]:
    """The parts of the gaps that fall inside [start, end)."""
    clipped = []
    for g in gaps:
        lo = g.start_unix if start is None else max(g.start_unix, start)
        hi = g.start_unix + g.missing_seconds
        hi = hi if end is None else min(hi, end)
        if hi > lo:
            clipped.append(Gap(start_unix=lo, missing_seconds=hi - lo))
    return tuple(clipped)


def _channel_indices(
    rec: Recording, scan: ScanResult, channels: Iterable[int] | None
) -> tuple[int, ...] | None:
    """Sorted selected indices, or None when they are all of the recording's channels."""
    stored = {c.channel_index for c in rec.channels}
    if channels is None:
        return None
    chosen = sorted(set(channels))
    if not chosen:
        raise SelectionError("Select at least one channel.")
    unknown = [i for i in chosen if i not in stored]
    if unknown:
        raise SelectionError(f"The recording has no channel {', '.join(map(str, unknown))}.")
    found = {c.channel_index for c in scan.channels}
    absent = [i for i in chosen if i not in found]
    if absent:
        raise SelectionError(
            f"Channel {', '.join(map(str, absent))} is not in the folder {scan.root}."
        )
    return None if set(chosen) == stored else tuple(chosen)


def _select_channel(ch: ChannelScan, start: float | None, end: float | None) -> ChannelSelection:
    files = tuple(
        SelectedFile(rel_path=rel_path(ch.sub_path, f.name), size=f.size, timestamp=f.timestamp)
        for f in ch.files
        if in_range(f.timestamp, start, end)
    )
    return ChannelSelection(
        channel_index=ch.channel_index,
        sub_path=ch.sub_path,
        files=files,
        gaps=clip_gaps(ch.gaps, start, end),
    )


def select_from_scan(
    rec: Recording,
    scan: ScanResult,
    *,
    channels: Iterable[int] | None = None,
    start_unix: float | None = None,
    end_unix: float | None = None,
) -> Selection:
    """The files of `scan` in the range and channels. channels None selects all.

    With channels None, every channel in the folder is selected, and a channel that
    is in the database but not in the folder is reported in `differences`.
    Raises SelectionError for an empty range, an unknown channel, or no files.
    """
    if start_unix is not None and end_unix is not None and end_unix <= start_unix:
        raise SelectionError("The end of the range must be after its start.")
    indices = _channel_indices(rec, scan, channels)
    chosen = (
        scan.channels
        if indices is None
        else [c for c in scan.channels if c.channel_index in indices]
    )
    selected = tuple(_select_channel(c, start_unix, end_unix) for c in chosen)
    if not any(c.files for c in selected):
        raise SelectionError("No files in the selected range and channels.")
    return Selection(
        recording_id=rec.id,
        source=scan.root,
        file_duration_s=scan.file_duration_s,
        range_start_unix=start_unix,
        range_end_unix=end_unix,
        channel_indices=indices,
        channels=selected,
        differences=tuple(scan_differences(rec, scan)),
        scan=scan,
    )


def select_files(
    rec: Recording,
    *,
    channels: Iterable[int] | None = None,
    start_unix: float | None = None,
    end_unix: float | None = None,
    folder: Path | None = None,
    progress: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Selection:
    """Rescan the recording's folder and select files from it (D53).

    folder defaults to the stored location. Raises the scanner's ScanError and
    ScanCancelled, and SelectionError.
    """
    source = recording_folder(rec) if folder is None else folder
    scan = scan_recording(source, rec.file_duration_s, progress=progress, cancelled=cancelled)
    return select_from_scan(rec, scan, channels=channels, start_unix=start_unix, end_unix=end_unix)
