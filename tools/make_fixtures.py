"""Generate synthetic IQ recordings for tests and manual testing.

A recording is a folder of fixed-duration data files named by Unix time, for
example 1790733600.dat. Multi-channel recordings put each channel in a numbered
subfolder (0/, 1/, ...). A single channel can also sit in the folder itself (--flat).

Time is divided into slots of one file duration each, numbered from 0 at the start
time. Gaps, channel spans and wrong-size files are given as slot numbers.

The tool only creates files. It opens every file in exclusive-create mode and refuses
an output folder that exists and is not empty, a drive root, or a network path.

Examples:
    python tools/make_fixtures.py fixtures_out/demo
    python tools/make_fixtures.py fixtures_out/multi --channels 3 --gap 4-5 --gap 1:8
    python tools/make_fixtures.py fixtures_out/big --files 50000 --content empty
    python tools/make_fixtures.py fixtures_out/bad --header-bytes 64 --wrong-size 0:3 --junk

Exit codes: 0 success, 1 output folder refused, 2 usage error.
"""

import argparse
import array
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_START_UNIX = 1790733600  # 2026-09-30T02:00:00Z
HEADER_MAGIC = b"IQDMFIX\0"
TONE_AMPLITUDE = 0.25  # fraction of full scale
TONE_PERIOD = 16  # samples; tone frequency = fs * (k / 16) with k in 1..7

# dtype -> (array typecode, bytes per sample, full-scale value)
DTYPES: dict[str, tuple[str, int, float]] = {
    "int8": ("b", 1, 127),
    "int16": ("h", 2, 32767),
    "int32": ("i", 4, 2147483647),
    "float32": ("f", 4, 1.0),
}
CONTENTS = ("tone", "zeros", "empty")
EXTENSIONS = (".dat", ".bin")


class SpecError(ValueError):
    """The recording specification is invalid."""


class OutputRefusedError(Exception):
    """The output folder is not safe to write into."""


@dataclass(frozen=True)
class ChannelSpec:
    """Per-channel overrides. Slots are file indices from the recording start."""

    first_slot: int = 0
    last_slot: int | None = None  # inclusive; None = last slot of the recording
    gaps: frozenset[int] = frozenset()
    wrong_size: dict[int, int | None] = field(default_factory=dict)  # None = half size


@dataclass(frozen=True)
class RecordingSpec:
    """What to generate. gaps and wrong_size here apply to every channel."""

    n_channels: int = 1
    n_slots: int = 10
    start_unix: float = DEFAULT_START_UNIX
    file_duration_s: float = 1.0
    fs_hz: float = 1000.0
    dtype: str = "int16"
    header_bytes: int = 0
    ext: str = ".dat"
    flat: bool = False
    content: str = "tone"
    junk: bool = False
    gaps: frozenset[int] = frozenset()
    wrong_size: dict[int, int | None] = field(default_factory=dict)
    channels: dict[int, ChannelSpec] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelInfo:
    """Ground truth for one generated channel."""

    index: int
    sub_path: str  # '' when the files sit in the recording folder
    timestamps: list[float]  # present files, sorted
    missing: list[float]  # absent slots between the first and last present file
    start_unix: float | None  # first file timestamp; None if the channel has no files
    end_unix: float | None  # exclusive: last file timestamp + file duration
    expected_file_bytes: int  # header + fs * duration * 2 * bytes per sample
    file_bytes: int  # actual size of each normal file (0 for empty content)
    wrong_size: dict[str, int]  # file name -> actual size
    n_files: int
    total_bytes: int


@dataclass(frozen=True)
class FixtureInfo:
    """Ground truth for a generated recording."""

    root: str
    file_duration_s: float
    fs_hz: float
    dtype: str
    header_bytes: int
    channels: list[ChannelInfo]
    unrecognised: list[str]  # paths relative to root, '/'-separated

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def samples_per_file(spec: RecordingSpec) -> int:
    """Complex samples per file. Raises SpecError unless fs * duration is whole."""
    n = spec.fs_hz * spec.file_duration_s
    if n <= 0 or abs(n - round(n)) > 1e-9:
        raise SpecError(
            f"fs_hz * file_duration_s must be a positive whole number of samples, got {n}"
        )
    return round(n)


def expected_file_bytes(spec: RecordingSpec) -> int:
    """Expected size of one data file: header + fs * duration * 2 * bytes per sample."""
    return spec.header_bytes + samples_per_file(spec) * 2 * DTYPES[spec.dtype][1]


def format_stem(t: float) -> str:
    """File stem for a timestamp: '1790733600' or '1790733600.5'."""
    if float(t).is_integer():
        return str(int(t))
    return f"{t:.6f}".rstrip("0").rstrip(".")


def _validate(spec: RecordingSpec) -> None:
    if spec.n_channels < 1:
        raise SpecError("n_channels must be at least 1")
    if spec.n_slots < 1:
        raise SpecError("n_slots must be at least 1")
    if spec.flat and spec.n_channels != 1:
        raise SpecError("flat layout needs exactly one channel")
    if spec.dtype not in DTYPES:
        raise SpecError(f"dtype must be one of {sorted(DTYPES)}")
    if spec.content not in CONTENTS:
        raise SpecError(f"content must be one of {CONTENTS}")
    if spec.ext not in EXTENSIONS:
        raise SpecError(f"ext must be one of {EXTENSIONS}")
    if spec.header_bytes < 0:
        raise SpecError("header_bytes must be >= 0")
    if spec.file_duration_s <= 0 or spec.fs_hz <= 0:
        raise SpecError("file_duration_s and fs_hz must be positive")
    samples_per_file(spec)

    for ch in spec.channels:
        if not 0 <= ch < spec.n_channels:
            raise SpecError(f"channel {ch} is out of range 0..{spec.n_channels - 1}")
    for ch in range(spec.n_channels):
        first, last = _span(spec, ch)
        if not 0 <= first <= last < spec.n_slots:
            raise SpecError(f"channel {ch}: span {first}-{last} is outside 0..{spec.n_slots - 1}")
        gaps = _gaps(spec, ch)
        for slot in gaps:
            if not 0 <= slot < spec.n_slots:
                raise SpecError(f"channel {ch}: gap slot {slot} is outside 0..{spec.n_slots - 1}")
        for slot, size in _wrong_size(spec, ch).items():
            if not first <= slot <= last or slot in gaps:
                raise SpecError(f"channel {ch}: wrong-size slot {slot} has no file")
            if size is not None and size < 0:
                raise SpecError(f"channel {ch}: wrong-size bytes must be >= 0")


def _span(spec: RecordingSpec, ch: int) -> tuple[int, int]:
    cs = spec.channels.get(ch, ChannelSpec())
    last = spec.n_slots - 1 if cs.last_slot is None else cs.last_slot
    return cs.first_slot, last


def _gaps(spec: RecordingSpec, ch: int) -> frozenset[int]:
    return spec.gaps | spec.channels.get(ch, ChannelSpec()).gaps


def _wrong_size(spec: RecordingSpec, ch: int) -> dict[int, int | None]:
    return {**spec.wrong_size, **spec.channels.get(ch, ChannelSpec()).wrong_size}


def _check_output_dir(out_dir: Path) -> Path:
    """Refuse network paths, roots and non-empty folders. Returns the resolved path."""
    raw = str(out_dir)
    if raw.startswith(("\\\\", "//")):
        raise OutputRefusedError(f"network paths are not allowed: {raw}")
    resolved = out_dir.resolve()
    if resolved.parent == resolved:
        raise OutputRefusedError(f"refusing to write into a filesystem root: {resolved}")
    if resolved.exists():
        if not resolved.is_dir():
            raise OutputRefusedError(f"output exists and is not a folder: {resolved}")
        if any(resolved.iterdir()):
            raise OutputRefusedError(f"output folder is not empty: {resolved}")
    return resolved


def _tone_period(spec: RecordingSpec, ch: int) -> list[float]:
    """One period of interleaved I, Q values for the channel's tone."""
    _, _, full_scale = DTYPES[spec.dtype]
    amplitude = TONE_AMPLITUDE * full_scale
    k = ch % 7 + 1
    values: list[float] = []
    for n in range(TONE_PERIOD):
        phase = 2 * math.pi * k * n / TONE_PERIOD
        i, q = amplitude * math.cos(phase), amplitude * math.sin(phase)
        if spec.dtype == "float32":
            values += [i, q]
        else:
            values += [round(i), round(q)]
    return values


def _payload(spec: RecordingSpec, period: list[float], slot: int, spf: int) -> bytes:
    """Sample data for one file, little-endian, continuous across files."""
    typecode, bytes_per_sample, _ = DTYPES[spec.dtype]
    if spec.content == "zeros":
        return bytes(spf * 2 * bytes_per_sample)
    offset = 2 * ((slot * spf) % TONE_PERIOD)
    rotated = period[offset:] + period[:offset]
    values = (rotated * (spf // TONE_PERIOD + 1))[: 2 * spf]
    arr = array.array(typecode, values)
    if arr.itemsize != bytes_per_sample:
        raise RuntimeError(f"array typecode {typecode!r} is not {bytes_per_sample} bytes here")
    if sys.byteorder != "little":
        arr.byteswap()
    return arr.tobytes()


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as f:  # fails if the file already exists
        f.write(data)


def make_recording(out_dir: Path, spec: RecordingSpec) -> FixtureInfo:
    """Create a synthetic recording in out_dir and return its ground truth."""
    _validate(spec)
    root = _check_output_dir(Path(out_dir))
    root.mkdir(parents=True, exist_ok=True)

    spf = samples_per_file(spec)
    expected = expected_file_bytes(spec)
    header = (HEADER_MAGIC + bytes(spec.header_bytes))[: spec.header_bytes]

    channels: list[ChannelInfo] = []
    for ch in range(spec.n_channels):
        sub_path = "" if spec.flat else str(ch)
        ch_dir = root / sub_path if sub_path else root
        ch_dir.mkdir(exist_ok=True)

        first, last = _span(spec, ch)
        gaps = _gaps(spec, ch)
        wrong = _wrong_size(spec, ch)
        period = _tone_period(spec, ch) if spec.content == "tone" else []

        timestamps: list[float] = []
        wrong_written: dict[str, int] = {}
        file_bytes = 0 if spec.content == "empty" else expected
        total = 0
        for slot in range(first, last + 1):
            if slot in gaps:
                continue
            t = spec.start_unix + slot * spec.file_duration_s
            name = format_stem(t) + spec.ext
            data = b"" if spec.content == "empty" else header + _payload(spec, period, slot, spf)
            if slot in wrong:
                size = wrong[slot]
                size = expected // 2 if size is None else size
                data = (data + bytes(max(0, size - len(data))))[:size]
                wrong_written[name] = size
            _write_new(ch_dir / name, data)
            timestamps.append(t)
            total += len(data)

        missing: list[float] = []
        if timestamps:
            present = {round((t - spec.start_unix) / spec.file_duration_s) for t in timestamps}
            lo, hi = min(present), max(present)
            missing = [
                spec.start_unix + s * spec.file_duration_s
                for s in range(lo, hi + 1)
                if s not in present
            ]
        channels.append(
            ChannelInfo(
                index=ch,
                sub_path=sub_path,
                timestamps=timestamps,
                missing=missing,
                start_unix=timestamps[0] if timestamps else None,
                end_unix=timestamps[-1] + spec.file_duration_s if timestamps else None,
                expected_file_bytes=expected,
                file_bytes=file_bytes,
                wrong_size=wrong_written,
                n_files=len(timestamps),
                total_bytes=total,
            )
        )

    unrecognised = _write_junk(root, spec) if spec.junk else []
    return FixtureInfo(
        root=str(root),
        file_duration_s=spec.file_duration_s,
        fs_hz=spec.fs_hz,
        dtype=spec.dtype,
        header_bytes=spec.header_bytes,
        channels=channels,
        unrecognised=unrecognised,
    )


def _write_junk(root: Path, spec: RecordingSpec) -> list[str]:
    """Add files a scanner must ignore. Returns their '/'-separated relative paths."""
    first_ch = "" if spec.flat else "0"
    rel_paths = [
        "notes.txt",
        "README",
        f"{first_ch}/{format_stem(spec.start_unix)}.tmp".lstrip("/"),
        f"{first_ch}/abc{spec.ext}".lstrip("/"),
    ]
    for rel in rel_paths:
        _write_new(root / rel, b"not IQ data\n")
    return rel_paths


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

_GAP_RE = re.compile(r"^(?:(\d+):)?(\d+)(?:-(\d+))?$")
_SPAN_RE = re.compile(r"^(\d+):(\d+)-(\d+)$")
_WRONG_RE = re.compile(r"^(?:(\d+):)?(\d+)(?:=(\d+))?$")


def _parse_gap(text: str) -> tuple[int | None, list[int]]:
    m = _GAP_RE.match(text)
    if not m:
        raise argparse.ArgumentTypeError(f"expected [CH:]A[-B], got {text!r}")
    ch = None if m[1] is None else int(m[1])
    a = int(m[2])
    b = a if m[3] is None else int(m[3])
    if b < a:
        raise argparse.ArgumentTypeError(f"gap end is before its start: {text!r}")
    return ch, list(range(a, b + 1))


def _parse_span(text: str) -> tuple[int, int, int]:
    m = _SPAN_RE.match(text)
    if not m:
        raise argparse.ArgumentTypeError(f"expected CH:FIRST-LAST, got {text!r}")
    return int(m[1]), int(m[2]), int(m[3])


def _parse_wrong_size(text: str) -> tuple[int | None, int, int | None]:
    m = _WRONG_RE.match(text)
    if not m:
        raise argparse.ArgumentTypeError(f"expected [CH:]SLOT[=BYTES], got {text!r}")
    ch = None if m[1] is None else int(m[1])
    return ch, int(m[2]), None if m[3] is None else int(m[3])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="make_fixtures.py",
        description="Generate a synthetic IQ recording folder.",
        epilog="Slots are file indices from the start time. Ranges A-B are inclusive.",
    )
    p.add_argument("out_dir", type=Path, help="recording folder to create (new or empty)")
    p.add_argument("--channels", type=int, default=1, help="number of channels (default 1)")
    p.add_argument("--files", type=int, default=10, help="file slots per channel (default 10)")
    p.add_argument("--start", type=float, default=DEFAULT_START_UNIX, help="start Unix time")
    p.add_argument("--file-duration", type=float, default=1.0, help="seconds per file")
    p.add_argument("--fs", type=float, default=1000.0, help="sample rate in Hz (default 1000)")
    p.add_argument("--dtype", choices=sorted(DTYPES), default="int16")
    p.add_argument("--header-bytes", type=int, default=0, help="header size per file")
    p.add_argument("--ext", choices=EXTENSIONS, default=".dat")
    p.add_argument("--flat", action="store_true", help="single channel files in the folder")
    p.add_argument("--content", choices=CONTENTS, default="tone")
    p.add_argument("--junk", action="store_true", help="add files a scanner must ignore")
    p.add_argument("--json", action="store_true", help="print ground truth as JSON")
    p.add_argument(
        "--gap", type=_parse_gap, action="append", default=[], metavar="[CH:]A[-B]",
        help="missing slots A..B; without CH, in every channel",
    )
    p.add_argument(
        "--span", type=_parse_span, action="append", default=[], metavar="CH:FIRST-LAST",
        help="channel CH has slots FIRST..LAST only",
    )
    p.add_argument(
        "--wrong-size", type=_parse_wrong_size, action="append", default=[],
        metavar="[CH:]SLOT[=BYTES]",
        help="file at SLOT gets BYTES bytes (default half the expected size)",
    )
    return p


def spec_from_args(args: argparse.Namespace) -> RecordingSpec:
    """Build a RecordingSpec from parsed command-line arguments."""
    all_gaps: set[int] = set()
    all_wrong: dict[int, int | None] = {}
    ch_gaps: dict[int, set[int]] = {}
    ch_wrong: dict[int, dict[int, int | None]] = {}
    ch_span: dict[int, tuple[int, int]] = {}

    for ch, slots in args.gap:
        (all_gaps if ch is None else ch_gaps.setdefault(ch, set())).update(slots)
    for ch, slot, size in args.wrong_size:
        (all_wrong if ch is None else ch_wrong.setdefault(ch, {}))[slot] = size
    for ch, first, last in args.span:
        ch_span[ch] = (first, last)

    channels: dict[int, ChannelSpec] = {}
    for ch in set(ch_gaps) | set(ch_wrong) | set(ch_span):
        first, last = ch_span.get(ch, (0, None))
        channels[ch] = ChannelSpec(
            first_slot=first,
            last_slot=last,
            gaps=frozenset(ch_gaps.get(ch, set())),
            wrong_size=ch_wrong.get(ch, {}),
        )

    return RecordingSpec(
        n_channels=args.channels,
        n_slots=args.files,
        start_unix=args.start,
        file_duration_s=args.file_duration,
        fs_hz=args.fs,
        dtype=args.dtype,
        header_bytes=args.header_bytes,
        ext=args.ext,
        flat=args.flat,
        content=args.content,
        junk=args.junk,
        gaps=frozenset(all_gaps),
        wrong_size=all_wrong,
        channels=channels,
    )


def _summary(info: FixtureInfo) -> str:
    lines = [f"Created {info.root}"]
    for c in info.channels:
        where = f"{c.sub_path}/" if c.sub_path else "(recording folder)"
        lines.append(f"  channel {c.index} {where}: {c.n_files} files, {c.total_bytes} bytes")
        if c.missing:
            lines.append(f"    missing: {', '.join(format_stem(t) for t in c.missing)}")
        if c.wrong_size:
            sizes = ", ".join(f"{name}={size}" for name, size in c.wrong_size.items())
            lines.append(f"    wrong size (expected {c.expected_file_bytes}): {sizes}")
    if info.unrecognised:
        lines.append(f"  unrecognised: {', '.join(info.unrecognised)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point. Returns the exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        spec = spec_from_args(args)
        info = make_recording(args.out_dir, spec)
    except SpecError as exc:
        parser.error(str(exc))  # exits with code 2
    except OutputRefusedError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(info.to_json() if args.json else _summary(info))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
