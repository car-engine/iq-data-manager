"""Shared pytest setup."""

import itertools
import os
from collections.abc import Callable
from pathlib import Path

import pytest

# Run Qt without a display so GUI tests open no windows. Set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# make_fixtures lives in tools/, which is on the pytest pythonpath (see pyproject.toml).
import make_fixtures
from iqdm.db.connection import create_database
from iqdm.models import Channel, Recording
from make_fixtures import FixtureInfo, RecordingSpec


@pytest.fixture
def db_path(tmp_path) -> Path:
    """A fresh database created from schema.sql under tmp_path."""
    path = tmp_path / "catalog.db"
    create_database(path)
    return path


@pytest.fixture
def make_recording(tmp_path) -> Callable[..., FixtureInfo]:
    """Factory that creates a synthetic recording in a new folder under tmp_path.

    Call with a RecordingSpec, or with RecordingSpec keyword arguments:
        info = make_recording(n_channels=2, gaps=frozenset({3}))
    """
    counter = itertools.count()

    def _make(spec: RecordingSpec | None = None, **kwargs) -> FixtureInfo:
        out = tmp_path / f"rec{next(counter)}"
        return make_fixtures.make_recording(out, spec or RecordingSpec(**kwargs))

    return _make


def recording_from(info: FixtureInfo, *, site_id: int = 1, **kw) -> Recording:
    """A catalogue entry that matches a generated recording, located where it lies."""
    root = Path(info.root)
    values = {
        "logged_by": "tester",
        "site_id": site_id,
        "storage_root": str(root.parent),
        "rel_path": root.name,
        "file_duration_s": info.file_duration_s,
        "channels": [
            Channel(
                channel_index=c.index,
                sub_path=c.sub_path,
                fc_hz=100e6 + c.index * 1e6,
                fs_hz=info.fs_hz,
                start_unix=c.start_unix,
                end_unix=c.end_unix,
                n_files=c.n_files,
                total_bytes=c.total_bytes,
            )
            for c in info.channels
            if c.start_unix is not None
        ],
    } | kw
    return Recording(**values)


def junction(link: Path, target: Path) -> Path:
    """A directory junction at `link` that points at `target`: one folder, two names.

    Junctions need no privilege on Windows. Tests that use one skip elsewhere. Both
    paths must lie under tmp_path.
    """
    if os.name != "nt":
        pytest.skip("directory junctions exist on Windows only")
    import _winapi

    link.parent.mkdir(parents=True, exist_ok=True)
    _winapi.CreateJunction(str(target), str(link))
    return link


@pytest.fixture
def entry_for() -> Callable[..., Recording]:
    """recording_from() as a fixture: entry_for(info, **Recording overrides)."""
    return recording_from


RECORDER_EXAMPLES = Path(__file__).parent / "data" / "recorder"


def recorder_log_text(
    channels: dict[int, tuple[float, float]],
    *,
    rate_msps: float = 0.001,
    ref: str = "gpsdo",
    files_written: int | None = None,
    sample_format: str = "sc16",
    subdev: str = "UBX RX",
    gps_locked: bool = True,
) -> str:
    """A recorder log in the format of the examples in tests/data/recorder (D82).

    channels maps a channel number to (frequency in MHz, gain in dB). The default rate,
    0.001 Msps, is the 1 kHz of make_fixtures' recordings.
    """
    t = "2026-10-12T03:25:14.243Z "
    lines = [
        f"{t}Command line: rx_samples_to_file_buffered.exe --ref {ref} --channels "
        + ",".join(str(i) for i in channels),
        f"{t}Using Device: Single USRP:",
        "  Device: X-Series Device",
        "  Mboard 0: X310",
    ]
    for i in range(4):
        lines += [f"  RX Channel: {i}", "    RX DSP: 0", f"    RX Subdev: {subdev}"]
    for i, (freq, gain) in channels.items():
        lines += [
            f"{t}Using channel {i} with antenna RX2",
            f"{t}Actual RX Rate: {rate_msps:.6f} Msps...",
            f"{t}Actual RX Freq: {freq:.6f} MHz...",
            f"{t}Actual RX Gain: {gain:.6f} dB...",
        ]
    lines.append(f"{t}EVENT lock sensor=gps_locked locked={1 if gps_locked else 0}")
    lines.append(f"{t}cpu_format: {sample_format} wire_format: {sample_format}")
    lines.append(f"{t}Time source {ref}, clock source {ref}")
    if ref == "internal":
        lines.append(f"{t}EVENT time_sync source=pc_now pc=1791801197.402646")
    if files_written is not None:
        lines.append(f"{t}Files written: {files_written}. Peak queue depth: 1 of 60.")
    lines.append(f"{t}Done! Stop reason: normal. Restarts: 0. Exit code: 0.")
    return "\n".join(lines) + "\n"
