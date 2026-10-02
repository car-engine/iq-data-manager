"""Log tab logic without Qt: form input, the validation checklist and saving.

SPEC section 6. The GUI collects an EntryInput, scans the folder with
iqdm.scan.scanner, then calls checklist() and save_new() or save_edit().
Rules: DECISIONS.md D2 (logging in place on the NAS), D14 (folder location),
D16 (edit mode) and D19 (input in MHz).
"""

import getpass
import itertools
import math
import re
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path, PureWindowsPath

from iqdm.db import repository
from iqdm.db.connection import Connection, open_db, write_transaction
from iqdm.location import Location, join_location
from iqdm.models import (
    BYTES_PER_SAMPLE,
    ArchiveState,
    Channel,
    Endianness,
    IqLayout,
    Operation,
    Param,
    Recording,
    SampleType,
    Site,
    TransferEntry,
    Verification,
)
from iqdm.scan.scanner import (
    NAMES_SHOWN,
    ChannelScan,
    ScanResult,
    Severity,
    check_channel,
    expected_file_bytes,
)
from iqdm.timeutil import utc_now_iso

IN_PLACE_NOTE = "logged in place, not verified against a source"  # DECISIONS.md D2
TIMES = "\N{MULTIPLICATION SIGN}"


COVERAGE_LIMIT_PERCENT = 100.0  # coverage above this, at one decimal place, is an error (D22)
SPACING_TOLERANCE = 0.01  # relative difference allowed between file spacing and duration (D22)


class ItemState(StrEnum):
    OK = "ok"
    INFO = "info"
    TODO = "todo"  # a field still to fill in (D23); blocks saving like an error
    ERROR = "error"


@dataclass(frozen=True)
class ChecklistItem:
    """One line of the "Before saving" checklist."""

    state: ItemState
    text: str


@dataclass(kw_only=True)
class ChannelInput:
    """What the user typed for one channel.

    fc is MHz text (D19). fs is text with an optional unit, Hz by default (D25).
    fs_inferred is True while fs holds the value worked out from the file size (D21).
    """

    channel_index: int
    band: str = ""
    fc_mhz: str = ""
    fs_text: str = ""
    fs_inferred: bool = False


@dataclass(kw_only=True)
class ParamInput:
    """One RF chain row as typed. channel_index None applies to the whole recording."""

    channel_index: int | None = None
    param: str = ""
    value: str = ""
    unit: str = ""

    @property
    def is_blank(self) -> bool:
        return not (self.param.strip() or self.value.strip() or self.unit.strip())


@dataclass(kw_only=True)
class EntryInput:
    """The Log tab form, apart from the folder.

    file_duration_inferred is True when the duration came from the file names (D22).
    """

    logged_by: str = ""
    site_id: int | None = None
    recording_plan_ref: str = ""
    remarks: str = ""
    file_duration_s: float = 1.0
    file_duration_inferred: bool = False
    dtype: SampleType = SampleType.INT16
    iq_layout: IqLayout = IqLayout.INTERLEAVED_IQ
    endianness: Endianness = Endianness.LITTLE
    header_bytes: int = 0
    channels: list[ChannelInput] = field(default_factory=list)
    params: list[ParamInput] = field(default_factory=list)

    def channel(self, index: int) -> ChannelInput | None:
        return next((c for c in self.channels if c.channel_index == index), None)


@dataclass(frozen=True, kw_only=True)
class ChannelChange:
    """Channel indices that a rescan in edit mode removes or adds (D16)."""

    removed: tuple[int, ...] = ()
    added: tuple[int, ...] = ()


@dataclass(frozen=True, kw_only=True)
class Choices:
    """Lists for the form's dropdowns and autocompletion."""

    sites: list[Site]
    param_names: list[str]
    bands: list[str]


# ---------------------------------------------------------------------------
# Text and number formats
# ---------------------------------------------------------------------------


def parse_mhz(text: str) -> float:
    """MHz text to Hz through Decimal, so '145.8' gives exactly 145800000.0 (D19).

    Raises ValueError with a short reason ('is empty', 'is not a number',
    'must be positive') unless the text is a positive finite number.
    """
    clean = text.strip()
    if not clean:
        raise ValueError("is empty")
    try:
        value = Decimal(clean)
    except InvalidOperation:
        raise ValueError(f"is not a number: {clean!r}") from None
    if not value.is_finite():
        raise ValueError(f"is not a number: {clean!r}")
    if value <= 0:
        raise ValueError(f"must be positive: {clean!r}")
    return float(value.scaleb(6))


def format_mhz(hz: float) -> str:
    """Hz as MHz text without trailing zeros: 145800000.0 gives '145.8'."""
    return format(Decimal(repr(float(hz))).scaleb(-6).normalize(), "f")


# Units accepted in the fs field, with their power of ten (DECISIONS.md D25).
# Letter case matters: 'm' would read as milli, so only 'M' means mega.
FREQUENCY_UNITS: dict[str, int] = {
    "": 0,
    "Hz": 0,
    "k": 3,
    "kHz": 3,
    "M": 6,
    "MHz": 6,
    "G": 9,
    "GHz": 9,
}
FREQUENCY_HELP = "a number in Hz, or with k, kHz, M, MHz, G or GHz, for example 12.5k or 10 MHz"
_FREQUENCY_RE = re.compile(r"^([0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?|[0-9]+\.)\s*([A-Za-z]*)$")


def parse_frequency(text: str) -> float:
    """fs text to Hz (D25). No unit means Hz. '100k', '100 kHz', '1.5M', '2 GHz'.

    The conversion goes through Decimal, so '12.5k' gives exactly 12500.0. Raises
    ValueError with a short reason ('is empty', 'is not understood: ...', 'must be
    positive: ...').
    """
    clean = text.strip()
    if not clean:
        raise ValueError("is empty")
    match = _FREQUENCY_RE.match(clean)
    if match is None or match.group(2) not in FREQUENCY_UNITS:
        raise ValueError(f"is not understood: {clean!r}. Enter {FREQUENCY_HELP}")
    value = Decimal(match.group(1)).scaleb(FREQUENCY_UNITS[match.group(2)])
    if value <= 0:
        raise ValueError(f"must be positive: {clean!r}")
    return float(value)


def format_frequency(hz: float) -> str:
    """Hz as text in the largest unit that keeps the number at 1 or more (D25).

    1000.0 gives '1 kHz', 12500.0 gives '12.5 kHz', 50e6 gives '50 MHz', 500.0 gives
    '500 Hz'. parse_frequency() reads every result back to the same value.
    """
    value = Decimal(repr(float(hz)))
    for unit, power in (("GHz", 9), ("MHz", 6), ("kHz", 3)):
        if abs(value) >= Decimal(10) ** power:
            return f"{format(value.scaleb(-power).normalize(), 'f')} {unit}"
    return f"{format(value.normalize(), 'f')} Hz"


def format_size(n_bytes: int) -> str:
    """Bytes in decimal units with one decimal place, for example '40.0 MB'."""
    if abs(n_bytes) < 1000:
        return f"{n_bytes} B"
    value = float(n_bytes)
    for unit in ("kB", "MB", "GB", "TB"):
        value /= 1000
        if abs(value) < 1000 or unit == "TB":
            break
    return f"{value:.1f} {unit}"


def _plural(n: int, word: str, plural: str | None = None) -> str:
    """'1 file', '7,197 files'."""
    return f"{n:,} {word if n == 1 else plural or word + 's'}"


def missing_text(seconds: float) -> str:
    """'1 missing second', '3 missing seconds', '0.5 missing seconds'."""
    return f"{seconds:g} missing second{'' if seconds == 1 else 's'}"


def _index_list(indices: Iterable[int]) -> str:
    return ", ".join(str(i) for i in indices)


def default_logged_by() -> str:
    """The login name of the current user, or '' if it cannot be found."""
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):
        return ""


# ---------------------------------------------------------------------------
# Scan and form
# ---------------------------------------------------------------------------


def with_file_duration(scan: ScanResult, file_duration_s: float) -> ScanResult:
    """The same scan with another file duration. No file is read again.

    Gaps and end times follow the new duration, so a change of the duration field
    needs no rescan (Milestone 2 report, issue 4). Raises ValueError for a duration
    that is not positive.
    """
    if not math.isfinite(file_duration_s) or file_duration_s <= 0:
        raise ValueError(f"file_duration_s must be positive, got {file_duration_s}")
    if file_duration_s == scan.file_duration_s:
        return scan
    return replace(
        scan,
        file_duration_s=file_duration_s,
        channels=tuple(replace(c, file_duration_s=file_duration_s) for c in scan.channels),
    )


@dataclass(frozen=True, kw_only=True)
class FsInference:
    """fs worked out from a channel's file size (DECISIONS.md D21).

    fs_hz is None when the size does not give a whole number of complex samples;
    reason then says why.
    """

    fs_hz: float | None
    file_bytes: int | None
    reason: str | None = None


def typical_file_bytes(channel: ChannelScan) -> int | None:
    """The most common file size of a channel, leaving out the last file (D3).

    A channel with one file uses that file. Ties go to the larger size. None for a
    channel with no files.
    """
    files = channel.files[:-1] if len(channel.files) > 1 else channel.files
    if not files:
        return None
    counts = Counter(f.size for f in files)
    return max(counts, key=lambda size: (counts[size], size))


def _header_text(header_bytes: int) -> str:
    return "no header" if header_bytes == 0 else f"a {header_bytes}-byte header"


def infer_fs(
    channel: ChannelScan,
    *,
    dtype: SampleType | str,
    header_bytes: int,
    file_duration_s: float,
) -> FsInference:
    """fs = (typical file size - header) / (2 * bytes per sample * file duration) (D21).

    The header is never guessed. Sample type, header and duration come from the form.
    """
    size = typical_file_bytes(channel)
    if size is None:
        return FsInference(fs_hz=None, file_bytes=None, reason="the channel has no data files")
    if not math.isfinite(file_duration_s) or file_duration_s <= 0:
        return FsInference(fs_hz=None, file_bytes=size, reason="the file duration is not positive")
    sample_type = SampleType(dtype)
    sample_bytes = 2 * BYTES_PER_SAMPLE[sample_type]
    payload = size - header_bytes
    if payload <= 0:
        return FsInference(
            fs_hz=None,
            file_bytes=size,
            reason=f"a {size}-byte file holds no samples after {_header_text(header_bytes)}",
        )
    if payload % sample_bytes:
        return FsInference(
            fs_hz=None,
            file_bytes=size,
            reason=(
                f"a {size}-byte file with {_header_text(header_bytes)} is not a whole number "
                f"of {sample_type} samples ({sample_bytes} bytes each). Check the sample type "
                "and header bytes"
            ),
        )
    samples = payload // sample_bytes
    fs = Decimal(samples) / Decimal(repr(float(file_duration_s)))
    return FsInference(fs_hz=float(fs), file_bytes=size)


def typical_spacing(scan: ScanResult) -> float | None:
    """Median step between consecutive file timestamps, over all channels (D22).

    Gaps barely move a median, so this is the file duration the names show. Rounded
    to 1 µs. None when no channel has two files.
    """
    steps = [
        b.timestamp - a.timestamp for ch in scan.channels for a, b in itertools.pairwise(ch.files)
    ]
    if not steps:
        return None
    return round(statistics.median(steps), 6)


def coverage_percent(
    n_files: int, file_duration_s: float, start: float, end: float
) -> float | None:
    """n_files * duration / span as a percentage at one decimal place, or None."""
    span = end - start
    if span <= 0:
        return None
    return round(100 * n_files * file_duration_s / span, 1)


def input_from_recording(rec: Recording) -> EntryInput:
    """The form for a stored recording (edit mode)."""
    return EntryInput(
        logged_by=rec.logged_by,
        site_id=rec.site_id,
        recording_plan_ref=rec.recording_plan_ref or "",
        remarks=rec.remarks or "",
        file_duration_s=rec.file_duration_s,
        dtype=rec.dtype,
        iq_layout=rec.iq_layout,
        endianness=rec.endianness,
        header_bytes=rec.header_bytes,
        channels=[
            ChannelInput(
                channel_index=c.channel_index,
                band=c.band or "",
                fc_mhz=format_mhz(c.fc_hz),
                fs_text=format_frequency(c.fs_hz),
            )
            for c in rec.channels
        ],
        params=[
            ParamInput(
                channel_index=p.channel_index,
                param=p.param,
                value=p.value,
                unit=p.unit or "",
            )
            for p in rec.params
        ],
    )


def channel_set_change(original: Recording, scan: ScanResult) -> ChannelChange:
    """Channels of the stored recording that a rescan removes, and channels it adds."""
    before = {c.channel_index for c in original.channels}
    after = {c.channel_index for c in scan.channels}
    return ChannelChange(removed=tuple(sorted(before - after)), added=tuple(sorted(after - before)))


def params_on_channels(rec: Recording, indices: Iterable[int]) -> int:
    """Number of the recording's parameters that belong to these channels."""
    wanted = set(indices)
    return sum(1 for p in rec.params if p.channel_index in wanted)


def params_without_channels(
    params: Sequence[ParamInput], indices: Iterable[int]
) -> list[ParamInput]:
    """The RF chain rows that do not belong to these channels (DECISIONS.md D20)."""
    dropped = set(indices)
    return [p for p in params if p.channel_index not in dropped]


_CHANNEL_NAME_RE = re.compile(r"^(0|[1-9][0-9]{0,2})$", re.ASCII)


def channel_like_parent(location: Location) -> str | None:
    """The parent folder if the folder is named like a channel folder, else None (D27).

    A name of 1 to 3 digits without a leading zero, such as '0' or '12', matches.
    Longer numbers, such as a Unix time, do not.
    """
    path = PureWindowsPath(location.full_path)
    if not _CHANNEL_NAME_RE.match(path.name):
        return None
    return str(path.parent)


def state_note(location: Location | None, original: Recording | None) -> str:
    """The line under the checklist that says which archive state a save writes."""
    if original is not None:
        return f"Editing recording {original.id}. The archive state stays {original.archive_state}."
    if location is None:
        return ""
    if location.archive_state is ArchiveState.ARCHIVED:
        return (
            "Archive state on save: archived. The transfer log will mark it as not verified "
            "against a source."
        )
    return "Archive state on save: local. Archive it to the NAS later from the Move / copy tab."


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------


def _channel_indices(scan: ScanResult | None, original: Recording | None) -> list[int]:
    if scan is not None:
        return [c.channel_index for c in scan.channels]
    if original is not None:
        return [c.channel_index for c in original.channels]
    return []


def _fs_hz(form: EntryInput, index: int) -> float | None:
    inp = form.channel(index)
    if inp is None:
        return None
    try:
        return parse_frequency(inp.fs_text)
    except ValueError:
        return None


def _scan_items(
    scan: ScanResult | None, original: Recording | None, scan_problems: Sequence[str]
) -> list[ChecklistItem]:
    if scan is None and scan_problems:
        return [
            ChecklistItem(
                ItemState.ERROR,
                f"The scan stopped with {_plural(len(scan_problems), 'problem')}. Fix the "
                f"folder and scan again: {'; '.join(scan_problems[:NAMES_SHOWN])}",
            )
        ]
    if scan is None:
        if original is None:
            return [ChecklistItem(ItemState.TODO, "Scan the folder")]
        return [
            ChecklistItem(
                ItemState.INFO, "Not rescanned: the stored file counts and times are kept"
            )
        ]
    n_files = sum(c.n_files for c in scan.channels)
    if n_files == 0:
        items = [ChecklistItem(ItemState.ERROR, "Folder scanned: no channel has data files")]
    else:
        items = [
            ChecklistItem(
                ItemState.OK,
                f"Folder scanned: {_plural(len(scan.channels), 'channel')}, "
                f"{_plural(n_files, 'file')}",
            )
        ]
    if original is not None:
        change = channel_set_change(original, scan)
        if change.removed:
            n_params = params_on_channels(original, change.removed)
            items.append(
                ChecklistItem(
                    ItemState.INFO,
                    f"The rescan removes channel {_index_list(change.removed)} and "
                    f"{_plural(n_params, 'parameter')}. Saving asks for confirmation.",
                )
            )
        if change.added:
            items.append(
                ChecklistItem(
                    ItemState.INFO, f"The rescan adds channel {_index_list(change.added)}."
                )
            )
    return items


def _duplicate_items(
    scan: ScanResult | None, logged_id: int | None, duplicate_checked: bool
) -> list[ChecklistItem]:
    if scan is None:
        return []
    if not duplicate_checked:
        return [ChecklistItem(ItemState.ERROR, "Not checked whether the folder is already logged")]
    if logged_id is None:
        return [ChecklistItem(ItemState.OK, "Folder not already in the database")]
    return [ChecklistItem(ItemState.ERROR, f"Folder already logged as recording {logged_id}")]


def _size_items(form: EntryInput, scan: ScanResult) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []
    expected: set[int] = set()
    all_checked = True
    any_error = False
    for ch in scan.channels:
        fs = _fs_hz(form, ch.channel_index)
        if not ch.files:
            # check_channel reports a channel with no files before it uses fs.
            items.append(
                ChecklistItem(
                    ItemState.ERROR,
                    check_channel(
                        ch, fs_hz=fs or 1.0, dtype=form.dtype, header_bytes=form.header_bytes
                    )[0].message,
                )
            )
            any_error = True
            continue
        if fs is None:
            all_checked = False  # the required-fields item reports the missing fs
            continue
        for finding in check_channel(
            ch, fs_hz=fs, dtype=form.dtype, header_bytes=form.header_bytes
        ):
            error = finding.severity is Severity.ERROR
            any_error = any_error or error
            items.append(
                ChecklistItem(ItemState.ERROR if error else ItemState.INFO, finding.message)
            )
        try:
            expected.add(expected_file_bytes(fs, ch.file_duration_s, form.dtype, form.header_bytes))
        except ValueError:
            any_error = True
    if all_checked and not any_error and scan.channels:
        factor = 2 * BYTES_PER_SAMPLE[form.dtype]
        if len(expected) == 1:
            text = (
                f"File sizes match fs {TIMES} {factor} bytes: "
                f"{format_size(next(iter(expected)))} per {scan.file_duration_s:g} s file"
            )
        else:
            text = f"File sizes match fs {TIMES} {factor} bytes in every channel"
        items.insert(0, ChecklistItem(ItemState.OK, text))
    return items


def _size_relevant_change(form: EntryInput, original: Recording) -> bool:
    """True if fs, sample type, header bytes or file duration differ from the stored values."""
    if (form.dtype, form.header_bytes, form.file_duration_s) != (
        original.dtype,
        original.header_bytes,
        original.file_duration_s,
    ):
        return True
    for ch in original.channels:
        fs = _fs_hz(form, ch.channel_index)
        if fs is not None and fs != ch.fs_hz:
            return True
    return False


def _required_items(form: EntryInput, indices: Sequence[int]) -> list[ChecklistItem]:
    """Empty fields are to-do items, grouped by field. Wrong values are errors (D23)."""
    items: list[ChecklistItem] = []
    if not form.logged_by.strip():
        items.append(ChecklistItem(ItemState.TODO, "Enter the logged-by name"))
    if form.site_id is None:
        items.append(ChecklistItem(ItemState.TODO, "Choose a site"))
    if not math.isfinite(form.file_duration_s) or form.file_duration_s <= 0:
        items.append(ChecklistItem(ItemState.ERROR, "File duration must be positive"))
    if form.header_bytes < 0:
        items.append(ChecklistItem(ItemState.ERROR, "Header bytes must be 0 or more"))
    fields = (
        ("fc (MHz)", lambda inp: inp.fc_mhz, parse_mhz),
        ("fs", lambda inp: inp.fs_text, parse_frequency),
    )
    for label, text_of, parse in fields:
        empty = []
        for index in indices:
            text = text_of(form.channel(index) or ChannelInput(channel_index=index))
            if not text.strip():
                empty.append(index)
                continue
            try:
                parse(text)
            except ValueError as exc:
                items.append(ChecklistItem(ItemState.ERROR, f"Channel {index}: {label} {exc}"))
        if empty:
            items.append(
                ChecklistItem(ItemState.TODO, f"Enter {label} for channel {_index_list(empty)}")
            )
    if not items:
        return [ChecklistItem(ItemState.OK, "Required fields filled")]
    return items


def _param_items(form: EntryInput, indices: Sequence[int]) -> list[ChecklistItem]:
    items = []
    for row, p in enumerate(form.params, start=1):
        if p.is_blank:
            continue
        name = p.param.strip()
        label = f"RF chain row {row}" + (f" ({name})" if name else "")
        if not name:
            items.append(ChecklistItem(ItemState.TODO, f"{label}: enter the parameter name"))
        if not p.value.strip():
            items.append(ChecklistItem(ItemState.TODO, f"{label}: enter a value"))
        if p.channel_index is not None and p.channel_index not in indices:
            items.append(
                ChecklistItem(
                    ItemState.ERROR,
                    f"{label}: channel {p.channel_index} is not in this recording",
                )
            )
    return items


def _spacing_items(form: EntryInput, scan: ScanResult) -> list[ChecklistItem]:
    """File duration against the spacing of the file names (D22)."""
    spacing = typical_spacing(scan)
    if spacing is None:
        return []
    duration = form.file_duration_s
    valid = math.isfinite(duration) and duration > 0
    if valid and abs(spacing - duration) > SPACING_TOLERANCE * duration:
        return [
            ChecklistItem(
                ItemState.ERROR,
                f"The file names are {spacing:g} s apart, but the file duration is "
                f"{duration:g} s. Set the file duration to match the files.",
            )
        ]
    if form.file_duration_inferred:
        return [
            ChecklistItem(
                ItemState.INFO,
                f"File duration set to {duration:g} s from the spacing of the file names.",
            )
        ]
    return []


def _coverage_items(
    channels: Iterable[tuple[int, int | None, float | None, float | None]], file_duration_s: float
) -> list[ChecklistItem]:
    """Coverage above 100.0 % is an error in every case (D22).

    channels holds (index, n_files, start, end) with an exclusive end.
    """
    items = []
    for index, n_files, start, end in channels:
        if n_files is None or start is None or end is None:
            continue
        percent = coverage_percent(n_files, file_duration_s, start, end)
        if percent is not None and percent > COVERAGE_LIMIT_PERCENT:
            items.append(
                ChecklistItem(
                    ItemState.ERROR,
                    f"Channel {index}: coverage is {percent:.1f}%, so the files overlap in "
                    "time. Check the file duration.",
                )
            )
    return items


def _fs_items(form: EntryInput, scan: ScanResult) -> list[ChecklistItem]:
    """Which fs values were filled in from the file size, and why others were not (D21)."""
    items = []
    filled: dict[tuple[str, int | None], list[int]] = {}
    for ch in scan.channels:
        inp = form.channel(ch.channel_index)
        if inp is not None and inp.fs_inferred and inp.fs_text.strip():
            try:
                fs_text = format_frequency(parse_frequency(inp.fs_text))
            except ValueError:
                fs_text = inp.fs_text.strip()
            filled.setdefault((fs_text, typical_file_bytes(ch)), []).append(ch.channel_index)
        elif (inp is None or not inp.fs_text.strip()) and ch.files:
            result = infer_fs(
                ch,
                dtype=form.dtype,
                header_bytes=form.header_bytes,
                file_duration_s=form.file_duration_s,
            )
            if result.reason is not None:
                items.append(
                    ChecklistItem(
                        ItemState.INFO,
                        f"Channel {ch.channel_index}: fs could not be filled in from the file "
                        f"size, because {result.reason}.",
                    )
                )
    for (fs_text, size), indices in filled.items():
        size_text = "" if size is None else f"{format_size(size)} per "
        items.insert(
            0,
            ChecklistItem(
                ItemState.INFO,
                f"fs filled in from the file size for channel {_index_list(indices)}: "
                f"{fs_text} ({size_text}{form.file_duration_s:g} s file, {form.dtype}, "
                f"{_header_text(form.header_bytes)}). Check it against the recording plan.",
            ),
        )
    return items


def _gap_items(scan: ScanResult) -> list[ChecklistItem]:
    items = []
    for ch in scan.channels:
        if ch.gaps:
            missing = sum(g.missing_seconds for g in ch.gaps)
            items.append(
                ChecklistItem(
                    ItemState.INFO,
                    f"Channel {ch.channel_index} has {missing_text(missing)} in "
                    f"{_plural(len(ch.gaps), 'gap')}. Ignore this if the gaps are expected.",
                )
            )
    return items


def _unrecognised_items(scan: ScanResult) -> list[ChecklistItem]:
    names = scan.unrecognised
    if not names:
        return []
    shown = ", ".join(names[:NAMES_SHOWN])
    rest = len(names) - NAMES_SHOWN
    if rest > 0:
        shown += f" and {rest} more"
    return [
        ChecklistItem(
            ItemState.INFO,
            f"{_plural(len(names), 'entry', 'entries')} not recognised and ignored: {shown}",
        )
    ]


def checklist(
    form: EntryInput,
    *,
    scan: ScanResult | None,
    location: Location | None = None,
    location_error: str | None = None,
    logged_id: int | None = None,
    duplicate_checked: bool = False,
    original: Recording | None = None,
    scan_problems: Sequence[str] = (),
) -> list[ChecklistItem]:
    """The "Before saving" checklist (SPEC section 6). Saving needs no ERROR or TODO item.

    scan_problems holds the problems of a scan that stopped (ScanError.problems).

    New entry: original is None, and scan, location and the duplicate check come from
    the scan worker. Edit mode (D16): original is the stored recording, scan is None
    until the user rescans, and the location is the stored one.
    """
    items: list[ChecklistItem] = []
    if location_error is not None:
        items.append(ChecklistItem(ItemState.ERROR, f"Folder cannot be logged: {location_error}"))
    items += _scan_items(scan, original, scan_problems)
    if original is None:
        items += _duplicate_items(scan, logged_id, duplicate_checked)
    if scan is not None:
        items += _size_items(form, scan)
    elif original is not None:
        if _size_relevant_change(form, original):
            items.append(
                ChecklistItem(
                    ItemState.ERROR,
                    "fs, sample type, header bytes or file duration changed: scan the folder "
                    "again before saving",
                )
            )
        else:
            items.append(
                ChecklistItem(
                    ItemState.INFO, "File sizes not checked: the folder was not rescanned"
                )
            )
    if scan is not None:
        items += _spacing_items(form, scan)
        items += _coverage_items(
            (
                (c.channel_index, c.n_files, c.start_unix, _end(c, form.file_duration_s))
                for c in scan.channels
            ),
            form.file_duration_s,
        )
        items += _fs_items(form, scan)
    elif original is not None:
        items += _coverage_items(
            ((c.channel_index, c.n_files, c.start_unix, c.end_unix) for c in original.channels),
            form.file_duration_s,
        )
    indices = _channel_indices(scan, original)
    items += _required_items(form, indices)
    items += _param_items(form, indices)
    if location is not None and location.outside_nas_roots and original is None:
        items.append(
            ChecklistItem(
                ItemState.INFO,
                "The folder is on a network share outside the configured NAS roots, "
                "so it is logged as local.",
            )
        )
    parent = None if location is None or original is not None else channel_like_parent(location)
    if parent is not None:
        items.insert(
            0,
            ChecklistItem(
                ItemState.INFO,
                f"This folder is named like a channel folder. If it belongs to a recording, "
                f"choose the parent folder: {parent}",
            ),
        )
    if scan is not None:
        items += _gap_items(scan)
        items += _unrecognised_items(scan)
    return items


def _end(channel: ChannelScan, file_duration_s: float) -> float | None:
    """Exclusive end of a scanned channel at the form's file duration."""
    return None if not channel.files else channel.files[-1].timestamp + file_duration_s


def can_save(items: Iterable[ChecklistItem]) -> bool:
    """True when no item is an error or still to do."""
    return all(i.state not in (ItemState.ERROR, ItemState.TODO) for i in items)


# ---------------------------------------------------------------------------
# Building and saving the recording
# ---------------------------------------------------------------------------


def _channel_from_scan(ch: ChannelScan, form: EntryInput) -> Channel:
    if ch.start_unix is None or ch.end_unix is None:
        raise ValueError(f"channel {ch.channel_index} has no data files")
    inp = form.channel(ch.channel_index) or ChannelInput(channel_index=ch.channel_index)
    return Channel(
        channel_index=ch.channel_index,
        sub_path=ch.sub_path,
        band=inp.band.strip() or None,
        fc_hz=parse_mhz(inp.fc_mhz),
        fs_hz=parse_frequency(inp.fs_text),
        start_unix=ch.start_unix,
        end_unix=ch.end_unix,
        n_files=ch.n_files,
        total_bytes=ch.total_bytes,
    )


def _channel_from_stored(ch: Channel, form: EntryInput) -> Channel:
    inp = form.channel(ch.channel_index) or ChannelInput(channel_index=ch.channel_index)
    return replace(
        ch,
        band=inp.band.strip() or None,
        fc_hz=parse_mhz(inp.fc_mhz),
        fs_hz=parse_frequency(inp.fs_text),
    )


def _params(form: EntryInput) -> list[Param]:
    return [
        Param(
            param=p.param.strip(),
            value=p.value.strip(),
            unit=p.unit.strip() or None,
            channel_index=p.channel_index,
        )
        for p in form.params
        if not p.is_blank
    ]


def build_recording(
    form: EntryInput,
    *,
    scan: ScanResult | None,
    location: Location | None = None,
    original: Recording | None = None,
) -> Recording:
    """The Recording to save. Call only when checklist() has no ERROR item.

    A new entry takes its channels from the scan and its location from `location`.
    In edit mode the location, archive state and archived_at stay as stored, and the
    channels come from the rescan if there is one (D16). Raises ValueError for input
    the checklist would reject.
    """
    if form.site_id is None:
        raise ValueError("no site chosen")
    if original is None:
        if scan is None or location is None:
            raise ValueError("a new entry needs a scan and a location")
        channels = [_channel_from_scan(c, form) for c in scan.channels]
        storage_root, rel_path = location.storage_root, location.rel_path
        archive_state, archived_at = location.archive_state, None
    else:
        if scan is not None:
            channels = [_channel_from_scan(c, form) for c in scan.channels]
        else:
            channels = [_channel_from_stored(c, form) for c in original.channels]
        storage_root, rel_path = original.storage_root, original.rel_path
        archive_state, archived_at = original.archive_state, original.archived_at
    return Recording(
        id=None if original is None else original.id,
        logged_by=form.logged_by.strip(),
        site_id=form.site_id,
        storage_root=storage_root,
        rel_path=rel_path,
        channels=channels,
        params=_params(form),
        file_duration_s=form.file_duration_s,
        dtype=form.dtype,
        iq_layout=form.iq_layout,
        endianness=form.endianness,
        header_bytes=form.header_bytes,
        archive_state=archive_state,
        archived_at=archived_at,
        recording_plan_ref=form.recording_plan_ref.strip() or None,
        remarks=form.remarks.strip() or None,
    )


def save_new(
    db_path: Path | str,
    rec: Recording,
    *,
    now: str | None = None,
    delays: Sequence[float] | None = None,
) -> int:
    """Insert a new recording in one transaction. Returns its id.

    A recording in a NAS folder (archive state archived) gets archived_at and the
    transfer_log row from DECISIONS.md D2 in the same transaction.
    """
    if rec.id is not None:
        raise ValueError("save_new needs a recording without an id")
    stamp = utc_now_iso() if now is None else now
    in_place = rec.archive_state is ArchiveState.ARCHIVED
    if in_place:
        rec = replace(rec, archived_at=stamp)

    def work(conn: Connection) -> int:
        recording_id = repository.insert_recording(conn, rec)
        if in_place:
            repository.insert_transfer(
                conn,
                TransferEntry(
                    recording_id=recording_id,
                    operation=Operation.CHECK,
                    source=join_location(rec.storage_root, rec.rel_path),
                    destination=None,
                    started_at=stamp,
                    finished_at=stamp,
                    performed_by=rec.logged_by,
                    verification=Verification.SKIPPED,
                    notes=IN_PLACE_NOTE,
                ),
            )
        return recording_id

    return write_transaction(db_path, work, delays=delays)


def save_edit(
    db_path: Path | str,
    rec: Recording,
    *,
    allow_channel_removal: bool = False,
    delays: Sequence[float] | None = None,
) -> None:
    """Update a stored recording in one transaction (D7, D16). Writes no transfer row."""
    if rec.id is None:
        raise ValueError("save_edit needs rec.id")
    write_transaction(
        db_path,
        lambda conn: repository.update_recording(
            conn, rec, allow_channel_removal=allow_channel_removal
        ),
        delays=delays,
    )


# ---------------------------------------------------------------------------
# Database reads and the site list
# ---------------------------------------------------------------------------


def load_choices(db_path: Path | str) -> Choices:
    """Sites, parameter names and bands, read on one read-only connection."""
    with open_db(db_path, readonly=True) as conn:
        return Choices(
            sites=repository.list_sites(conn),
            param_names=repository.list_param_names(conn),
            bands=repository.list_bands(conn),
        )


def find_logged(db_path: Path | str, location: Location) -> int | None:
    """Id of the recording already logged at this location, or None."""
    with open_db(db_path, readonly=True) as conn:
        return repository.find_recording_by_location(conn, location.storage_root, location.rel_path)


def load_recording(db_path: Path | str, recording_id: int) -> Recording:
    with open_db(db_path, readonly=True) as conn:
        return repository.get_recording(conn, recording_id)


def add_site(db_path: Path | str, name: str, *, delays: Sequence[float] | None = None) -> Site:
    """Add a site. Raises DuplicateSiteError if the name exists, ignoring case."""
    return write_transaction(db_path, lambda conn: repository.add_site(conn, name), delays=delays)
