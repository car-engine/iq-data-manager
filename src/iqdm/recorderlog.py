"""Values from the recording task's log files, for the Log tab (DECISIONS.md D82).

The recorder (rx_samples_to_file_buffered) writes three files at the top of a
recording folder:

- `recorder_<folder>.log`: the command line, the device, and per channel the actual
  rate, frequency and gain ("Using channel N with antenna ..." starts a channel's
  block; N is the channel folder's name), the sample format, the time and clock
  source, GPS lock, files written and how the run ended;
- `log.txt`: the command line alone;
- `check_quick.txt`: the recorder's own check of the files ("RESULT: PASS").

The main log is read first; values it lacks come from the command line in log.txt.
Nothing here is required: an unreadable or missing log fills nothing. No Qt here.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path

from iqdm.entry import (
    ChecklistItem,
    EntryInput,
    ItemState,
    ParamInput,
    format_frequency,
    format_mhz,
    parse_mhz,
)
from iqdm.models import SampleType
from iqdm.scan.scanner import ScanResult
from iqdm.templates import LogTemplate

MAIN_LOG_RE = re.compile(r"^recorder_.*\.log$", re.IGNORECASE)
COMMAND_FILE = "log.txt"
CHECK_FILE = "check_quick.txt"
MAX_LOG_BYTES = 20_000_000  # a log larger than this is not read

GAIN_PARAM = "USRP gain"  # the catalogue's spelling (review of 1.1.0, finding 3)
CLOCK_PARAM = "Clock reference"
DEVICE_PARAM = "USRP"
SAMPLE_TYPES = {"sc16": SampleType.INT16, "sc8": SampleType.INT8, "fc32": SampleType.FLOAT32}
CLOCK_NAMES = {"gpsdo": "GPSDO", "internal": "Internal", "external": "External"}
FROM_LOG_TOOLTIP = "Filled in from the recorder's log. Type a value to replace it."

_STAMP = r"^(?:\d{4}-\d\d-\d\dT[\d:.]+Z\s+)?"
_CHANNEL_RE = re.compile(_STAMP + r"Using channel (\d+) with antenna (\S+)")
_RATE_RE = re.compile(_STAMP + r"Actual RX Rate: ([\d.]+) Msps")
_FREQ_RE = re.compile(_STAMP + r"Actual RX Freq: ([\d.]+) MHz")
_GAIN_RE = re.compile(_STAMP + r"Actual RX Gain: (-?[\d.]+) dB")
_FORMAT_RE = re.compile(_STAMP + r"cpu_format: (\w+)")
_SOURCE_RE = re.compile(_STAMP + r"Time source (\w+), clock source (\w+)")
_PC_CLOCK_RE = re.compile(r"time_sync source=pc_now|Timestamps come from the PC clock")
_GPS_RE = re.compile(r"EVENT lock sensor=gps_locked locked=(\d)")
_FILES_RE = re.compile(_STAMP + r"Files written: (\d+)\.")
_DONE_RE = re.compile(r"Stop reason: (\w+)\. Restarts: (\d+)\. Exit code: (-?\d+)\.")
_COMMAND_RE = re.compile(_STAMP + r"Command line: (.*)$")
_MBOARD_RE = re.compile(r"^\s+Mboard \d+: (.+?)\s*$")
_RX_CHANNEL_RE = re.compile(r"^\s+RX Channel: (\d+)\s*$")
_RX_SUBDEV_RE = re.compile(r"^\s+RX Subdev: (.+?)\s*$")
_RESULT_RE = re.compile(r"^RESULT: (\w+)", re.MULTILINE)


@dataclass
class LogChannel:
    index: int
    rate_hz: float | None = None
    freq_hz: float | None = None
    gain_db: float | None = None
    daughterboard: str | None = None


@dataclass
class RecorderLog:
    """What the log files say. Every value is optional."""

    files: list[str] = field(default_factory=list)  # the log files read
    channels: dict[int, LogChannel] = field(default_factory=dict)
    sample_format: str | None = None  # 'sc16', as the recorder names it
    clock_source: str | None = None
    time_source: str | None = None
    pc_clock: bool = False  # the times came from the PC clock
    gps_locked: bool | None = None  # None: no GPS lock was asked for
    mboard: str | None = None
    files_written: int | None = None
    stop_reason: str | None = None
    restarts: int | None = None
    exit_code: int | None = None
    verdict: str | None = None  # check_quick's RESULT
    problems: list[str] = field(default_factory=list)  # why a file could not be used

    @property
    def found(self) -> bool:
        return bool(self.files)

    def channel(self, index: int) -> LogChannel:
        return self.channels.setdefault(index, LogChannel(index=index))


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _read(path: Path, log: RecorderLog) -> str | None:
    try:
        if path.stat().st_size > MAX_LOG_BYTES:
            log.problems.append(f"{path.name} is too large to read")
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.problems.append(f"cannot read {path.name}: {exc.strerror or exc}")
        return None


def read_folder(folder: Path, side_files: Sequence[str]) -> RecorderLog:
    """Read the recorder's files among `side_files`, the names at the top of `folder`.

    The main log is `recorder_<folder name>.log`, or the only `recorder_*.log`.
    """
    log = RecorderLog()
    mains = [n for n in side_files if MAIN_LOG_RE.match(n)]
    main = next((n for n in mains if n.lower() == f"recorder_{folder.name}.log".lower()), None)
    if main is None and len(mains) == 1:
        main = mains[0]
    elif main is None and len(mains) > 1:
        log.problems.append(
            f"{len(mains)} recorder logs and none named after the folder: {', '.join(mains)}"
        )
    if main is not None and (text := _read(folder / main, log)) is not None:
        log.files.append(main)
        parse_main_log(text, log)
    command = next((n for n in side_files if n.lower() == COMMAND_FILE), None)
    if command is not None and (text := _read(folder / command, log)) is not None:
        log.files.append(command)
        parse_command_line(text, log, fill_only=True)
    check = next((n for n in side_files if n.lower() == CHECK_FILE), None)
    if check is not None and (text := _read(folder / check, log)) is not None:
        log.files.append(check)
        parse_check(text, log)
    return log


def parse_main_log(text: str, log: RecorderLog) -> None:
    """The recorder's own log. Later lines replace earlier ones, as after a restart."""
    current: LogChannel | None = None
    device_channel: int | None = None
    for line in text.splitlines():
        if m := _COMMAND_RE.match(line):
            parse_command_line(m.group(1), log, fill_only=True)
        elif m := _MBOARD_RE.match(line):
            log.mboard = m.group(1)
        elif m := _RX_CHANNEL_RE.match(line):
            device_channel = int(m.group(1))
        elif (m := _RX_SUBDEV_RE.match(line)) and device_channel is not None:
            log.channel(device_channel).daughterboard = _board_name(m.group(1))
            device_channel = None
        elif m := _CHANNEL_RE.match(line):
            current = log.channel(int(m.group(1)))
        elif (m := _RATE_RE.match(line)) and current is not None:
            current.rate_hz = _scaled(m.group(1), 6)
        elif (m := _FREQ_RE.match(line)) and current is not None:
            current.freq_hz = _scaled(m.group(1), 6)
        elif (m := _GAIN_RE.match(line)) and current is not None:
            current.gain_db = float(m.group(1))
        elif m := _FORMAT_RE.match(line):
            log.sample_format = m.group(1).lower()
        elif m := _SOURCE_RE.match(line):
            log.time_source, log.clock_source = m.group(1).lower(), m.group(2).lower()
        elif m := _GPS_RE.search(line):
            log.gps_locked = m.group(1) == "1"
        elif m := _FILES_RE.match(line):
            log.files_written = int(m.group(1))
        elif m := _DONE_RE.search(line):
            log.stop_reason = m.group(1)
            log.restarts, log.exit_code = int(m.group(2)), int(m.group(3))
        if _PC_CLOCK_RE.search(line):
            log.pc_clock = True
    _drop_unused_channels(log)


def _drop_unused_channels(log: RecorderLog) -> None:
    """The device summary lists every channel of the device; keep the recorded ones."""
    recorded = {i for i, c in log.channels.items() if c.freq_hz is not None}
    if recorded:
        log.channels = {i: c for i, c in log.channels.items() if i in recorded}


def _board_name(subdev: str) -> str:
    """'UBX RX' -> 'UBX', 'TwinRX RX0' -> 'TwinRX'."""
    m = re.match(r"^(.*?)\s+RX\d*$", subdev)
    return m.group(1) if m else subdev


def _scaled(text: str, power: int) -> float:
    """A decimal number times 10**power, exact: '300.000000' MHz -> 300e6 Hz."""
    return float(Decimal(text).scaleb(power))


def _numbers(text: str) -> list[float]:
    return [float(Decimal(part)) for part in text.split(",") if part.strip()]


def _option(args: list[str], name: str) -> str | None:
    try:
        return args[args.index(name) + 1]
    except (ValueError, IndexError):
        return None


def parse_command_line(text: str, log: RecorderLog, *, fill_only: bool = False) -> None:
    """The recorder's command line. With fill_only, values already known stay."""
    args = text.split()
    try:
        indices = [int(x) for x in (_option(args, "--channels") or "0").split(",") if x]
        rate = _option(args, "--rate")
        freqs = _numbers(_option(args, "--freq") or "")
        gains = _numbers(_option(args, "--gain") or "")
        rate_hz = float(Decimal(rate)) if rate else None
    except (ValueError, ArithmeticError):
        log.problems.append("the command line holds a value that is not a number")
        return
    for n, index in enumerate(indices):
        ch = log.channel(index)
        if rate_hz is not None and (ch.rate_hz is None or not fill_only):
            ch.rate_hz = rate_hz
        freq = freqs[n] if n < len(freqs) else (freqs[-1] if len(freqs) == 1 else None)
        if freq is not None and (ch.freq_hz is None or not fill_only):
            ch.freq_hz = freq
        gain = gains[n] if n < len(gains) else (gains[-1] if len(gains) == 1 else None)
        if gain is not None and (ch.gain_db is None or not fill_only):
            ch.gain_db = gain
    ref = _option(args, "--ref")
    if ref and (log.clock_source is None or not fill_only):
        log.clock_source = ref.lower()


def parse_check(text: str, log: RecorderLog) -> None:
    if m := _RESULT_RE.search(text):
        log.verdict = m.group(1).upper()
    if log.sample_format is None and (m := re.search(r"\btype (\w+)", text)):
        log.sample_format = m.group(1).lower()


# ---------------------------------------------------------------------------
# Values for the form
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class FormValues:
    """What a scan of a new entry fills in from the log (D82)."""

    dtype: SampleType | None = None
    fc_mhz: dict[int, str] = field(default_factory=dict)  # by channel folder number
    fs_text: dict[int, str] = field(default_factory=dict)
    params: tuple[ParamInput, ...] = ()  # USRP gain, Clock reference, and USRP if none
    filled: tuple[str, ...] = ()  # what was filled, for the checklist line


def _number_text(value: float) -> str:
    """30.0 -> '30', 31.5 -> '31.5'."""
    return format(Decimal(repr(value)).normalize(), "f")


def _spelling(name: str, known_names: Sequence[str]) -> str:
    """The catalogue's spelling of a parameter name, or `name` when it holds none (D28)."""
    wanted = name.casefold()
    return next((k.strip() for k in known_names if k.strip().casefold() == wanted), name)


def form_values(
    log: RecorderLog,
    channel_indices: Sequence[int],
    params: Sequence[ParamInput],
    known_names: Sequence[str] = (),
) -> FormValues:
    """The values to fill for the scanned channels. `params` are the form's RF chain rows.

    A "USRP" row comes from the log only when the form has none, so a template's
    "USRP-2954" stays: the log cannot tell that unit from an X310 with UBX boards.
    The rows take the spelling of `known_names`, the names already in the catalogue,
    so the checklist does not report a spelling the save would change (D28).
    """
    gain_param = _spelling(GAIN_PARAM, known_names)
    clock_param = _spelling(CLOCK_PARAM, known_names)
    device_param = _spelling(DEVICE_PARAM, known_names)
    channels = [log.channels[i] for i in channel_indices if i in log.channels]
    filled: list[str] = []
    dtype = SAMPLE_TYPES.get(log.sample_format or "")
    if dtype is not None:
        filled.append(f"sample type {dtype}")
    fc = {c.index: format_mhz(c.freq_hz) for c in channels if c.freq_hz is not None}
    fs = {c.index: format_frequency(c.rate_hz) for c in channels if c.rate_hz is not None}
    if fc:
        filled.append(f"fc of {_channel_words(fc)}")
    if fs:
        filled.append(f"fs of {_channel_words(fs)}")
    rows: list[ParamInput] = []
    gains = {c.index: c.gain_db for c in channels if c.gain_db is not None}
    if gains:
        if len(set(gains.values())) == 1:
            value = _number_text(next(iter(gains.values())))
            rows.append(ParamInput(param=gain_param, value=value, unit="dB"))
        else:
            rows += [
                ParamInput(channel_index=i, param=gain_param, value=_number_text(g), unit="dB")
                for i, g in sorted(gains.items())
            ]
        filled.append(gain_param)
    if log.clock_source:
        name = CLOCK_NAMES.get(log.clock_source, log.clock_source)
        rows.append(ParamInput(param=clock_param, value=name))
        filled.append(clock_param)
    has_device = any(p.param.strip().casefold() == DEVICE_PARAM.casefold() for p in params)
    if log.mboard and not has_device:
        boards = sorted({c.daughterboard for c in channels if c.daughterboard})
        value = log.mboard + (f" + {'/'.join(boards)}" if boards else "")
        rows.append(ParamInput(param=device_param, value=value))
        filled.append(device_param)
    return FormValues(dtype=dtype, fc_mhz=fc, fs_text=fs, params=tuple(rows), filled=tuple(filled))


def _channel_words(values: dict[int, str]) -> str:
    indices = sorted(values)
    word = "channel" if len(indices) == 1 else "channels"
    return f"{word} {', '.join(str(i) for i in indices)}"


def merge_params(current: Sequence[ParamInput], from_log: Sequence[ParamInput]) -> list[ParamInput]:
    """The form's RF chain rows with the log's rows in place.

    Every row (of any scope) named like a row from the log is replaced by the log's
    rows, so a gain kept per channel from the last folder does not override the log's
    gain for the whole recording (D28). Other rows stay in their order.
    """
    names = {p.param.casefold() for p in from_log}
    kept = [p for p in current if p.param.strip().casefold() not in names]
    return kept + list(from_log)


# ---------------------------------------------------------------------------
# A template imported after the log filled the form (DECISIONS.md D87)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Conflict:
    """A value the log filled in that a template holds otherwise. The texts are for the user."""

    what: str  # 'fc of channel 0', 'sample type', 'USRP gain'
    log_text: str
    template_text: str


def _row_key(p: ParamInput) -> tuple[int | None, str, str, str]:
    """An RF chain row without letter case and surrounding spaces, as D28 compares."""
    return (
        p.channel_index,
        p.param.strip().casefold(),
        p.value.strip().casefold(),
        p.unit.strip().casefold(),
    )


def _row_name(p: ParamInput) -> str:
    return p.param.strip() + ("" if p.channel_index is None else f" (Ch {p.channel_index})")


def _value_text(p: ParamInput) -> str:
    return f"{p.value.strip()} {p.unit.strip()}".strip()


def log_rows_in_form(values: FormValues, form: EntryInput) -> list[ParamInput]:
    """The RF chain rows the log filled in that the form still holds unchanged."""
    present = {_row_key(p) for p in form.params}
    return [p for p in values.params if _row_key(p) in present]


def _same_mhz(a: str, b: str) -> bool:
    try:
        return parse_mhz(a) == parse_mhz(b)
    except ValueError:
        return a.strip() == b.strip()


def template_conflicts(values: FormValues, form: EntryInput, tpl: LogTemplate) -> list[Conflict]:
    """The values from the log, still in the form, that importing `tpl` would replace.

    A value the user typed over no longer counts as from the log. A template value equal
    to the log's is no conflict.
    """
    conflicts: list[Conflict] = []
    if (
        tpl.sample_type is not None
        and values.dtype is not None
        and form.dtype == values.dtype
        and tpl.sample_type != values.dtype
    ):
        conflicts.append(Conflict("sample type", str(values.dtype), str(tpl.sample_type)))
    if tpl.channels is not None:
        by_index = {c.index: c for c in tpl.channels}
        for c in form.channels:
            t = by_index.get(c.channel_index)
            if t is None or not c.fc_from_log or _same_mhz(c.fc_mhz, t.fc_mhz):
                continue
            conflicts.append(
                Conflict(
                    f"fc of channel {c.channel_index}",
                    f"{c.fc_mhz.strip()} MHz",
                    f"{t.fc_mhz.strip()} MHz" if t.fc_mhz.strip() else "empty",
                )
            )
    if tpl.rf_chain is not None:
        in_template = {_row_key(p) for p in tpl.rf_chain}
        for p in log_rows_in_form(values, form):
            if _row_key(p) in in_template:
                continue
            name = p.param.strip().casefold()
            others = [q for q in tpl.rf_chain if q.param.strip().casefold() == name]
            conflicts.append(
                Conflict(
                    _row_name(p),
                    _value_text(p),
                    ", ".join(_value_text(q) for q in others) or "no row",
                )
            )
    return conflicts


def keep_log_values(tpl: LogTemplate, values: FormValues, form: EntryInput) -> LogTemplate:
    """`tpl` changed so that importing it keeps the values from the log in the form.

    The template's sample type is left out, the fc of channels filled from the log is
    the form's, and the log's RF chain rows replace the template's rows of those names.
    """
    out = tpl
    if values.dtype is not None and form.dtype == values.dtype:
        out = replace(out, sample_type=None)
    if out.channels is not None:
        log_fc = {c.channel_index: c.fc_mhz for c in form.channels if c.fc_from_log}
        out = replace(
            out,
            channels=tuple(
                replace(c, fc_mhz=log_fc[c.index]) if c.index in log_fc else c
                for c in out.channels
            ),
        )
    if out.rf_chain is not None:
        rows = merge_params(out.rf_chain, log_rows_in_form(values, form))
        out = replace(out, rf_chain=tuple(rows))
    return out


def still_filled(values: FormValues, form: EntryInput) -> tuple[str, ...]:
    """What the form still holds from the log, for the checklist line.

    A value typed over, or replaced by a template, drops out (D87).
    """
    filled: list[str] = []
    if values.dtype is not None and form.dtype == values.dtype:
        filled.append(f"sample type {values.dtype}")
    fc = {c.channel_index: "" for c in form.channels if c.fc_from_log}
    fs = {c.channel_index: "" for c in form.channels if c.fs_from_log}
    if fc:
        filled.append(f"fc of {_channel_words(fc)}")
    if fs:
        filled.append(f"fs of {_channel_words(fs)}")
    for p in log_rows_in_form(values, form):
        if p.param not in filled:
            filled.append(p.param)
    return tuple(filled)


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------


def checklist_items(
    log: RecorderLog | None, scan: ScanResult | None, filled: Sequence[str] = ()
) -> list[ChecklistItem]:
    """Information lines about the recorder's log (D82). None of them blocks saving."""
    if log is None or (not log.found and not log.problems):
        return []
    items: list[ChecklistItem] = []
    if log.problems:
        items.append(
            ChecklistItem(
                ItemState.INFO,
                "The recorder's log could not be used, so some values were not filled in: "
                + "; ".join(log.problems),
            )
        )
    if filled:
        items.append(
            ChecklistItem(
                ItemState.INFO,
                f"Filled in from the recorder's log: {', '.join(filled)}. Check them against "
                "the recording task.",
            )
        )
    if log.verdict == "PASS":
        items.append(ChecklistItem(ItemState.OK, "The recorder's own check passed"))
    elif log.verdict:
        items.append(ChecklistItem(ItemState.INFO, f"The recorder's own check says {log.verdict}"))
    if log.pc_clock:
        items.append(
            ChecklistItem(
                ItemState.INFO,
                "The recorder took its times from the PC clock, not from GPS. File times are "
                "only as accurate as that PC's clock.",
            )
        )
    if log.gps_locked is False:
        items.append(ChecklistItem(ItemState.INFO, "The recorder's log says GPS was not locked."))
    if log.restarts:
        times = "time" if log.restarts == 1 else "times"
        items.append(
            ChecklistItem(ItemState.INFO, f"The recorder restarted {log.restarts} {times}.")
        )
    if log.stop_reason and log.stop_reason != "normal":
        items.append(
            ChecklistItem(
                ItemState.INFO, f"The recorder stopped for this reason: {log.stop_reason}."
            )
        )
    if log.files_written is not None and scan is not None:
        found = sum(c.n_files for c in scan.channels)
        if found != log.files_written:
            lost = log.files_written - found
            detail = (
                f" {lost:,} {'file' if lost == 1 else 'files'} went missing after recording."
                if lost > 0
                else ""
            )
            items.append(
                ChecklistItem(
                    ItemState.INFO,
                    f"The recorder wrote {log.files_written:,} files; the folder holds "
                    f"{found:,}.{detail}",
                )
            )
    return items
