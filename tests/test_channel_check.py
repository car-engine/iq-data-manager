"""Tests for check_channel() and expected_file_bytes() (SPEC section 6, D3, D11, D12)."""

from pathlib import Path

import pytest

import make_fixtures
from iqdm.models import SampleType
from iqdm.scan.scanner import (
    ChannelScan,
    Finding,
    Severity,
    check_channel,
    expected_file_bytes,
    scan_recording,
)
from make_fixtures import ChannelSpec, FixtureInfo, RecordingSpec


def scanned(info: FixtureInfo) -> tuple[ChannelScan, ...]:
    return scan_recording(Path(info.root), info.file_duration_s).channels


def check(ch: ChannelScan, info: FixtureInfo) -> list[Finding]:
    return check_channel(ch, fs_hz=info.fs_hz, dtype=info.dtype, header_bytes=info.header_bytes)


def write_files(folder: Path, names: list[str], size: int = 0) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        with (folder / name).open("xb") as f:
            f.write(bytes(size))


# ---------------------------------------------------------------------------
# expected_file_bytes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fs_hz", "duration", "dtype", "header", "expected"),
    [
        (1000, 1.0, SampleType.INT8, 0, 2000),
        (1000, 1.0, SampleType.INT16, 0, 4000),
        (1000, 1.0, SampleType.FLOAT32, 0, 8000),
        (1000, 1.0, SampleType.INT16, 64, 4064),
        (1000, 0.5, "int16", 0, 2000),
        (50e6, 1.0, "int16", 0, 200_000_000),  # SPEC section 2: 200 MB at 50 MS/s
        (61.44e6, 0.1, "int16", 0, 24_576_000),
    ],
)
def test_expected_file_bytes(fs_hz, duration, dtype, header, expected):
    assert expected_file_bytes(fs_hz, duration, dtype, header) == expected


def test_expected_file_bytes_agrees_with_make_fixtures():
    for dtype in ("int8", "int16", "float32"):
        spec = RecordingSpec(dtype=dtype, header_bytes=16, fs_hz=2000, file_duration_s=0.25)
        assert expected_file_bytes(2000, 0.25, dtype, 16) == make_fixtures.expected_file_bytes(spec)


@pytest.mark.parametrize(
    ("fs_hz", "duration", "header", "match"),
    [
        (1000.5, 1.0, 0, "whole number of samples"),
        (1000, 0.0001, 0, "whole number of samples"),
        (0, 1.0, 0, "whole number of samples"),
        (-1000, 1.0, 0, "whole number of samples"),
        (float("nan"), 1.0, 0, "whole number of samples"),
        (1000, 1.0, -1, "header_bytes"),
    ],
)
def test_expected_file_bytes_rejects(fs_hz, duration, header, match):
    with pytest.raises(ValueError, match=match):
        expected_file_bytes(fs_hz, duration, "int16", header)


def test_expected_file_bytes_rejects_an_unknown_sample_type():
    with pytest.raises(ValueError, match="int32"):
        expected_file_bytes(1000, 1.0, "int32", 0)


# ---------------------------------------------------------------------------
# Sizes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dtype", ["int8", "int16", "float32"])
def test_correct_sizes_give_no_findings(make_recording, dtype):
    info = make_recording(n_channels=2, dtype=dtype, header_bytes=32, gaps=frozenset({3}))
    for ch in scanned(info):
        assert check(ch, info) == []


def test_short_last_file_is_information(make_recording):
    info = make_recording(wrong_size={9: 1000})
    (ch,) = scanned(info)
    assert check(ch, info) == [
        Finding(
            severity=Severity.INFO,
            channel_index=0,
            message=(
                "channel 0 (folder 0): the last file 1790733609.dat is 1000 bytes, shorter "
                "than the expected 4000 bytes"
            ),
        )
    ]


def test_large_last_file_is_an_error(make_recording):
    info = make_recording(wrong_size={9: 4002})
    (ch,) = scanned(info)
    (finding,) = check(ch, info)
    assert finding.severity == Severity.ERROR
    assert "1790733609.dat (4002 bytes)" in finding.message


def test_short_first_file_is_an_error(make_recording):
    info = make_recording(wrong_size={0: None})
    (ch,) = scanned(info)
    (finding,) = check(ch, info)
    assert finding.severity == Severity.ERROR
    assert "1790733600.dat (2000 bytes)" in finding.message


def test_short_single_file_is_an_error(make_recording):
    info = make_recording(n_slots=1, wrong_size={0: None})
    (ch,) = scanned(info)
    (finding,) = check(ch, info)
    assert finding.severity == Severity.ERROR


def test_wrong_size_names_channel_file_and_sizes(make_recording):
    info = make_recording(n_channels=2, channels={1: ChannelSpec(wrong_size={4: 3998})})
    ch0, ch1 = scanned(info)
    assert check(ch0, info) == []
    assert check(ch1, info) == [
        Finding(
            severity=Severity.ERROR,
            channel_index=1,
            message=(
                "channel 1 (folder 1): 1 files differ from the expected size of 4000 bytes: "
                "1790733604.dat (3998 bytes)"
            ),
        )
    ]


def test_wrong_size_and_short_last_file_together(make_recording):
    info = make_recording(wrong_size={2: 10, 9: 10})
    (ch,) = scanned(info)
    error, info_finding = check(ch, info)
    assert error.severity == Severity.ERROR
    assert "1 files differ" in error.message
    assert info_finding.severity == Severity.INFO


def test_many_wrong_sizes_are_one_finding(make_recording):
    info = make_recording(n_slots=20, wrong_size={s: 10 for s in range(1, 13)})
    (ch,) = scanned(info)
    (finding,) = check(ch, info)
    assert "12 files differ" in finding.message
    assert finding.message.endswith("1790733610.dat (10 bytes) and 2 more")


def test_flat_channel_label(make_recording):
    info = make_recording(flat=True, wrong_size={3: 1})
    (ch,) = scanned(info)
    (finding,) = check(ch, info)
    assert finding.message.startswith("channel 0 (recording folder): ")


def test_empty_files_are_all_wrong(make_recording):
    info = make_recording(content="empty")
    (ch,) = scanned(info)
    (finding,) = check(ch, info)
    assert "10 files differ" in finding.message


@pytest.mark.parametrize(
    ("header_bytes", "last_size", "severity"),
    [
        (0, 0, Severity.ERROR),
        (0, 1, Severity.INFO),
        (64, 0, Severity.ERROR),
        (64, 63, Severity.ERROR),
        (64, 64, Severity.ERROR),
        (64, 65, Severity.INFO),
    ],
)
def test_last_file_without_iq_data_is_an_error(make_recording, header_bytes, last_size, severity):
    info = make_recording(header_bytes=header_bytes, wrong_size={9: last_size})
    (ch,) = scanned(info)
    (finding,) = check(ch, info)
    assert finding.severity == severity
    assert "1790733609.dat" in finding.message
    assert f"{last_size} bytes" in finding.message


def test_fs_that_is_not_whole_samples_is_an_error(make_recording):
    info = make_recording()
    (ch,) = scanned(info)
    (finding,) = check_channel(ch, fs_hz=1000.5, dtype="int16", header_bytes=0)
    assert finding.severity == Severity.ERROR
    assert "whole number of samples" in finding.message


def test_channel_with_no_files_is_an_error(make_recording):
    info = make_recording()
    (Path(info.root) / "1").mkdir()
    _, ch1 = scanned(info)
    assert check(ch1, info) == [
        Finding(
            severity=Severity.ERROR,
            channel_index=1,
            message="channel 1 (folder 1) has no data files",
        )
    ]


def test_each_channel_checks_against_its_own_fs(tmp_path):
    rec = tmp_path / "rec"
    make_fixtures.make_recording(rec / "0", RecordingSpec(flat=True, fs_hz=1000))
    make_fixtures.make_recording(rec / "1", RecordingSpec(flat=True, fs_hz=2000))
    ch0, ch1 = scan_recording(rec, 1.0).channels
    assert check_channel(ch0, fs_hz=1000, dtype="int16", header_bytes=0) == []
    assert check_channel(ch1, fs_hz=2000, dtype="int16", header_bytes=0) == []
    (finding,) = check_channel(ch1, fs_hz=1000, dtype="int16", header_bytes=0)
    assert "expected size of 4000 bytes" in finding.message


# ---------------------------------------------------------------------------
# File spacing (DECISIONS.md D12)
# ---------------------------------------------------------------------------


def test_files_closer_than_half_the_duration_are_an_error(tmp_path):
    stems = ["1790733600", "1790733600.25", "1790733601", "1790733601.4"]
    write_files(tmp_path, [f"{s}.dat" for s in stems], size=4000)
    (ch,) = scan_recording(tmp_path, 1.0).channels
    (finding,) = check_channel(ch, fs_hz=1000, dtype="int16", header_bytes=0)
    assert finding == Finding(
        severity=Severity.ERROR,
        channel_index=0,
        message=(
            "channel 0 (recording folder): 2 pairs of files are closer together than half "
            "the file duration of 1 s: 1790733600.dat and 1790733600.25.dat, "
            "1790733601.dat and 1790733601.4.dat. Check the file duration."
        ),
    )


def test_files_half_a_duration_apart_are_allowed(tmp_path):
    write_files(tmp_path, ["1790733600.dat", "1790733600.5.dat"], size=4000)
    (ch,) = scan_recording(tmp_path, 1.0).channels
    assert check_channel(ch, fs_hz=1000, dtype="int16", header_bytes=0) == []


def test_wrong_file_duration_is_reported(make_recording):
    info = make_recording(file_duration_s=0.25, fs_hz=4000)
    ch = scan_recording(Path(info.root), 1.0).channels[0]
    findings = check_channel(ch, fs_hz=4000, dtype="int16", header_bytes=0)
    assert [f.severity for f in findings] == [Severity.ERROR, Severity.INFO, Severity.ERROR]
    assert "9 files differ from the expected size of 16000 bytes" in findings[0].message
    assert findings[2].message.endswith("Check the file duration.")
