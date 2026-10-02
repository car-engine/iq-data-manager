"""Dataclasses and enums passed between the database, scanner, transfer and GUI layers.

No SQL and no Qt here. Enum values match the CHECK constraints in db/schema.sql.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

# transfer_log.notes of the row written when a folder on the NAS is logged in place.
# The Viewer marks such a recording as not verified (DECISIONS.md D2).
IN_PLACE_NOTE = "logged in place, not verified against a source"


class SampleType(StrEnum):
    INT8 = "int8"
    INT16 = "int16"
    FLOAT32 = "float32"


BYTES_PER_SAMPLE: dict[SampleType, int] = {
    SampleType.INT8: 1,
    SampleType.INT16: 2,
    SampleType.FLOAT32: 4,
}


class IqLayout(StrEnum):
    INTERLEAVED_IQ = "interleaved_iq"
    INTERLEAVED_QI = "interleaved_qi"
    PLANAR_IQ = "planar_iq"


class Endianness(StrEnum):
    LITTLE = "little"
    BIG = "big"


class ArchiveState(StrEnum):
    LOCAL = "local"
    ARCHIVED = "archived"


class Operation(StrEnum):
    MOVE = "move"
    COPY = "copy"
    CHECK = "check"
    DELETE = "delete"  # the laptop copy after a passed move (DECISIONS.md D52)


class Verification(StrEnum):
    PASS = "pass"  # noqa: S105  (not a password)
    FAIL = "fail"
    SKIPPED = "skipped"


class HashMode(StrEnum):
    NONE = "none"
    SAMPLE = "sample"
    ALL = "all"


@dataclass(kw_only=True)
class Site:
    name: str
    id: int | None = None
    created_at: str | None = None


@dataclass(kw_only=True)
class Channel:
    """One channel of a recording. end_unix is exclusive."""

    channel_index: int
    fc_hz: float
    fs_hz: float
    start_unix: float
    end_unix: float
    sub_path: str = ""
    band: str | None = None
    n_files: int | None = None
    total_bytes: int | None = None
    id: int | None = None


@dataclass(kw_only=True)
class Param:
    """One RF chain row. channel_index None applies to the whole recording."""

    param: str
    value: str
    unit: str | None = None
    channel_index: int | None = None
    id: int | None = None


@dataclass(kw_only=True)
class Recording:
    """A capture session with its channels and RF chain parameters.

    The repository sets id, date, start_unix, end_unix, created_at and updated_at
    on read. On write it derives date, start_unix and end_unix from the channels and
    ignores the values given here.
    """

    logged_by: str
    site_id: int
    storage_root: str
    rel_path: str
    channels: list[Channel]
    params: list[Param] = field(default_factory=list)
    file_duration_s: float = 1.0
    dtype: SampleType = SampleType.INT16
    iq_layout: IqLayout = IqLayout.INTERLEAVED_IQ
    endianness: Endianness = Endianness.LITTLE
    header_bytes: int = 0
    archive_state: ArchiveState = ArchiveState.LOCAL
    archived_at: str | None = None
    recording_plan_ref: str | None = None
    remarks: str | None = None
    id: int | None = None
    date: str | None = None
    start_unix: float | None = None
    end_unix: float | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, kw_only=True)
class RecordingSummary:
    """One row of the recordings list."""

    id: int
    date: str
    start_unix: float
    end_unix: float
    site_name: str
    channel_count: int
    fc_hz: tuple[float, ...]  # by channel index
    total_bytes: int | None  # None if any channel's size is unknown
    coverage: float | None  # minimum across channels; None if any is undefined
    archive_state: ArchiveState
    logged_by: str
    unverified: bool = False  # archived in place on the NAS, never checked (D2)


@dataclass(frozen=True, kw_only=True)
class RecordingFilter:
    """Viewer filters. None leaves a filter out; all given filters must match.

    Start bounds apply to the recording's start: from inclusive, before exclusive.
    Band and the fc range must match on the same channel. Text filters match a part of
    the text, ignoring letter case for ASCII letters. RF chain text matches a
    parameter's name, value or unit.
    """

    start_from_unix: float | None = None
    start_before_unix: float | None = None
    site_id: int | None = None
    band: str | None = None
    fc_min_hz: float | None = None
    fc_max_hz: float | None = None
    archive_state: ArchiveState | None = None
    rf_chain_text: str | None = None
    remarks_text: str | None = None


@dataclass(kw_only=True)
class TransferEntry:
    """One transfer_log row. channels None means all channels.

    parent_id is set exactly for a delete row and names the move it follows (D52).
    """

    recording_id: int
    operation: Operation
    source: str
    started_at: str
    performed_by: str
    destination: str | None = None
    range_start_unix: float | None = None
    range_end_unix: float | None = None
    channels: tuple[int, ...] | None = None
    hash_mode: HashMode | None = None
    finished_at: str | None = None
    n_files: int | None = None
    total_bytes: int | None = None
    verification: Verification = Verification.SKIPPED
    notes: str | None = None
    parent_id: int | None = None
    manifest_path: str | None = None
    manifest_sha256: str | None = None
    id: int | None = None


def channel_coverage(channel: Channel, file_duration_s: float) -> float | None:
    """n_files * file_duration_s / span, or None if n_files is unknown or span is zero."""
    span = channel.end_unix - channel.start_unix
    if channel.n_files is None or span <= 0:
        return None
    return channel.n_files * file_duration_s / span


def recording_coverage(channels: Sequence[Channel], file_duration_s: float) -> float | None:
    """Minimum channel coverage, or None if there are no channels or any is undefined."""
    values = [channel_coverage(c, file_duration_s) for c in channels]
    if not values or any(v is None for v in values):
        return None
    return min(v for v in values if v is not None)


def envelope(channels: Sequence[Channel]) -> tuple[float, float]:
    """Earliest channel start and latest channel end. Raises ValueError if empty."""
    if not channels:
        raise ValueError("a recording needs at least one channel")
    return min(c.start_unix for c in channels), max(c.end_unix for c in channels)
