"""Tests for the recording folder scanner: detection, listing, gaps and scale.

The channel check (check_channel, expected_file_bytes) is in test_channel_check.py.
Folders that make_fixtures cannot produce are built with write_files() under tmp_path.
"""

import dataclasses
import os
from collections.abc import Iterable
from pathlib import Path

import pytest

import make_fixtures
from iqdm.scan.scanner import (
    PROGRESS_EVERY,
    ChannelScan,
    Gap,
    ScanCancelled,
    ScanError,
    scan_recording,
)
from make_fixtures import ChannelInfo, ChannelSpec, FixtureInfo, RecordingSpec, format_stem

T0 = make_fixtures.DEFAULT_START_UNIX


def write_files(folder: Path, names: Iterable[str], size: int = 0) -> None:
    """Create new files of `size` zero bytes. Fails if a file already exists."""
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        with (folder / name).open("xb") as f:
            f.write(bytes(size))


def scan(info: FixtureInfo, **kwargs) -> tuple[ChannelScan, ...]:
    return scan_recording(Path(info.root), info.file_duration_s, **kwargs).channels


def gap_runs(missing: list[float], dur: float) -> list[Gap]:
    """Group the ground truth's missing timestamps into runs of consecutive slots."""
    runs: list[Gap] = []
    for t in missing:
        if runs and abs(runs[-1].start_unix + runs[-1].missing_seconds - t) < 1e-6:
            last = runs.pop()
            runs.append(Gap(start_unix=last.start_unix, missing_seconds=last.missing_seconds + dur))
        else:
            runs.append(Gap(start_unix=t, missing_seconds=dur))
    return runs


def flat(gaps: Iterable[Gap]) -> list[float]:
    """Gaps as a flat list of numbers, for pytest.approx."""
    return [x for g in gaps for x in (g.start_unix, g.missing_seconds)]


def assert_matches(ch: ChannelScan, truth: ChannelInfo) -> None:
    """Compare a scanned channel with make_fixtures' ground truth."""
    assert ch.channel_index == truth.index
    assert ch.sub_path == truth.sub_path
    assert list(ch.timestamps) == truth.timestamps
    assert ch.start_unix == truth.start_unix
    assert ch.end_unix == truth.end_unix
    assert ch.n_files == truth.n_files
    assert ch.total_bytes == truth.total_bytes
    assert flat(ch.gaps) == pytest.approx(flat(gap_runs(truth.missing, ch.file_duration_s)))


# ---------------------------------------------------------------------------
# Channel detection
# ---------------------------------------------------------------------------


def test_flat_recording_is_channel_0_in_the_recording_folder(make_recording):
    info = make_recording(flat=True)
    (ch,) = scan(info)
    assert (ch.channel_index, ch.sub_path) == (0, "")
    assert_matches(ch, info.channels[0])


def test_single_channel_in_folder_0(make_recording):
    info = make_recording()
    (ch,) = scan(info)
    assert (ch.channel_index, ch.sub_path) == (0, "0")
    assert_matches(ch, info.channels[0])


def test_three_channels(make_recording):
    info = make_recording(n_channels=3)
    channels = scan(info)
    assert [c.channel_index for c in channels] == [0, 1, 2]
    for ch, truth in zip(channels, info.channels, strict=True):
        assert_matches(ch, truth)


def test_channel_index_is_the_folder_number(tmp_path):
    rec = tmp_path / "rec"
    for name in ("0", "2", "10"):
        make_fixtures.make_recording(rec / name, RecordingSpec(flat=True))
    channels = scan_recording(rec, 1.0).channels
    assert [(c.channel_index, c.sub_path) for c in channels] == [(0, "0"), (2, "2"), (10, "10")]


def test_data_files_next_to_channel_folders_are_an_error(make_recording):
    info = make_recording(n_channels=2)
    write_files(Path(info.root), ["1790733600.dat", "1790733601.dat"])
    with pytest.raises(ScanError) as exc_info:
        scan(info)
    (problem,) = exc_info.value.problems
    assert "recording folder next to channel folders" in problem
    assert "1790733600.dat, 1790733601.dat" in problem


@pytest.mark.parametrize("name", ["01", "00", "007"])
def test_channel_folder_with_leading_zero_is_an_error(tmp_path, name):
    write_files(tmp_path / "rec" / "0", ["1790733600.dat"])
    write_files(tmp_path / "rec" / name, ["1790733600.dat"])
    with pytest.raises(ScanError) as exc_info:
        scan_recording(tmp_path / "rec", 1.0)
    (problem,) = exc_info.value.problems
    assert problem == f"channel folder name has a leading zero: {name}"


def test_scan_error_lists_every_problem(tmp_path):
    rec = tmp_path / "rec"
    write_files(rec, ["1790733600.dat"])
    write_files(rec / "01", ["1790733600.dat"])
    write_files(rec / "0", ["1790733600.dat", "1790733600.bin"])
    write_files(rec / "1", ["1790733601.dat", "1790733601.0.dat"])
    with pytest.raises(ScanError) as exc_info:
        scan_recording(rec, 1.0)
    assert len(exc_info.value.problems) == 4
    assert str(exc_info.value) == "\n".join(exc_info.value.problems)


def test_other_folders_are_unrecognised(make_recording):
    info = make_recording()
    root = Path(info.root)
    (root / "logs").mkdir()
    (root / "0" / "nested").mkdir()
    (root / "-1").mkdir()
    result = scan_recording(root, 1.0)
    assert len(result.channels) == 1
    assert result.unrecognised == ("-1/", "0/nested/", "logs/")


def test_other_folders_are_unrecognised_in_a_flat_recording(make_recording):
    info = make_recording(flat=True)
    (Path(info.root) / "logs").mkdir()
    result = scan_recording(Path(info.root), 1.0)
    assert result.channels[0].sub_path == ""
    assert result.unrecognised == ("logs/",)


def test_empty_channel_folder_is_a_channel_with_no_files(make_recording):
    info = make_recording()
    (Path(info.root) / "1").mkdir()
    ch0, ch1 = scan(info)
    assert ch0.n_files == 10
    assert (ch1.channel_index, ch1.sub_path, ch1.n_files) == (1, "1", 0)
    assert (ch1.start_unix, ch1.end_unix, ch1.last_file_bytes) == (None, None, None)
    assert (ch1.total_bytes, ch1.sizes, ch1.gaps) == (0, frozenset(), ())


def test_empty_folder_has_no_channels(tmp_path):
    result = scan_recording(tmp_path, 1.0)
    assert (result.channels, result.unrecognised) == ((), ())


def test_folder_with_only_other_files_has_no_channels(tmp_path):
    write_files(tmp_path, ["notes.txt", "Thumbs.db"])
    result = scan_recording(tmp_path, 1.0)
    assert result.channels == ()
    assert result.unrecognised == ("Thumbs.db", "notes.txt")


def test_missing_folder_is_an_error(tmp_path):
    with pytest.raises(ScanError, match="folder not found"):
        scan_recording(tmp_path / "nothing", 1.0)


def test_file_instead_of_folder_is_an_error(tmp_path):
    write_files(tmp_path, ["1790733600.dat"])
    with pytest.raises(ScanError, match="not a folder"):
        scan_recording(tmp_path / "1790733600.dat", 1.0)


def test_symbolic_links_are_unrecognised(make_recording):
    info = make_recording()
    root = Path(info.root)
    try:
        (root / "1").symlink_to(root / "0", target_is_directory=True)
        (root / "0" / "1790733700.dat").symlink_to(root / "0" / "1790733600.dat")
    except OSError:
        pytest.skip("creating symbolic links needs a privilege this account lacks")
    result = scan_recording(root, 1.0)
    assert len(result.channels) == 1
    assert result.channels[0].n_files == 10
    assert result.unrecognised == ("0/1790733700.dat", "1")


# ---------------------------------------------------------------------------
# File listing
# ---------------------------------------------------------------------------


def test_both_extensions_in_any_letter_case(tmp_path):
    names = ["1790733600.dat", "1790733601.bin", "1790733602.DAT", "1790733603.Bin"]
    write_files(tmp_path, names)
    (ch,) = scan_recording(tmp_path, 1.0).channels
    assert [f.name for f in ch.files] == names
    assert ch.timestamps == (T0, T0 + 1, T0 + 2, T0 + 3)


def test_custom_extensions(tmp_path):
    write_files(tmp_path, ["1790733600.iq", "1790733601.IQ", "1790733602.dat"])
    result = scan_recording(tmp_path, 1.0, extensions=[".iq"])
    assert [f.name for f in result.channels[0].files] == ["1790733600.iq", "1790733601.IQ"]
    assert result.unrecognised == ("1790733602.dat",)


@pytest.mark.parametrize("extensions", [(), ("dat",), (".",)])
def test_malformed_extensions_are_rejected(tmp_path, extensions):
    with pytest.raises(ValueError, match="extensions"):
        scan_recording(tmp_path, 1.0, extensions=extensions)


@pytest.mark.parametrize("flat", [False, True])
def test_junk_files_are_unrecognised(make_recording, flat):
    info = make_recording(junk=True, flat=flat)
    result = scan_recording(Path(info.root), 1.0)
    assert result.unrecognised == tuple(sorted(info.unrecognised))
    assert_matches(result.channels[0], info.channels[0])


@pytest.mark.parametrize(
    "name",
    [
        "abc.dat",
        "x.tmp",
        "-5.dat",
        "+5.dat",
        "1e9.dat",
        "1790733600..dat",
        "1790733600.5.5.dat",
        ".5.dat",
        "1790733600.dat.part",
        "1790733600",
        ".dat",
        " 1790733600.dat",
        "".join(chr(0xFF10 + int(d)) for d in "1790") + ".dat",  # full-width digits
    ],
)
def test_names_that_are_not_data_files(tmp_path, name):
    write_files(tmp_path, ["1790733600.dat", name])
    result = scan_recording(tmp_path, 1.0)
    assert result.channels[0].n_files == 1
    assert result.unrecognised == (name,)


def test_fractional_timestamps(make_recording):
    info = make_recording(start_unix=T0 + 0.5, file_duration_s=0.5, gaps=frozenset({3}))
    (ch,) = scan(info)
    assert ch.files[1].name == "1790733601.dat"
    assert ch.start_unix == T0 + 0.5
    assert_matches(ch, info.channels[0])


def test_timestamps_sort_numerically_across_a_digit_boundary(make_recording):
    info = make_recording(start_unix=999_999_998, n_slots=5, flat=True)
    (ch,) = scan(info)
    assert ch.timestamps == (999_999_998, 999_999_999, 1_000_000_000, 1_000_000_001, 1_000_000_002)


@pytest.mark.parametrize(
    "pair",
    [
        ("1790733600.bin", "1790733600.dat"),
        ("1790733600.0.dat", "1790733600.dat"),
    ],
)
def test_same_timestamp_twice_is_an_error(tmp_path, pair):
    write_files(tmp_path / "0", ["1790733601.dat", *pair])
    with pytest.raises(ScanError) as exc_info:
        scan_recording(tmp_path, 1.0)
    (problem,) = exc_info.value.problems
    assert problem == f"channel 0 (folder 0): 1 timestamps appear twice: {pair[0]} and {pair[1]}"


@pytest.mark.parametrize("dtype", ["int8", "int16", "float32"])
@pytest.mark.parametrize("header_bytes", [0, 64])
def test_sizes_match_ground_truth(make_recording, dtype, header_bytes):
    info = make_recording(
        n_channels=2,
        dtype=dtype,
        header_bytes=header_bytes,
        gaps=frozenset({4}),
        channels={1: ChannelSpec(wrong_size={2: None, 9: 100})},
    )
    for ch, truth in zip(scan(info), info.channels, strict=True):
        assert_matches(ch, truth)
        assert ch.sizes == {truth.file_bytes, *truth.wrong_size.values()}
        last_name = format_stem(truth.timestamps[-1]) + ".dat"
        assert ch.last_file_bytes == truth.wrong_size.get(last_name, truth.file_bytes)
    assert scan(info)[1].last_file_bytes == 100


def test_channel_spans_match_ground_truth(make_recording):
    info = make_recording(
        n_channels=3,
        n_slots=20,
        channels={
            0: ChannelSpec(first_slot=3, last_slot=12),
            1: ChannelSpec(gaps=frozenset({0, 1, 5, 19})),
            2: ChannelSpec(first_slot=10),
        },
    )
    channels = scan(info)
    for ch, truth in zip(channels, info.channels, strict=True):
        assert_matches(ch, truth)
    assert channels[0].gaps == ()
    assert channels[1].gaps == (Gap(start_unix=T0 + 5, missing_seconds=1.0),)


def test_result_records_the_folder_and_duration(make_recording):
    info = make_recording(file_duration_s=0.5)
    result = scan_recording(Path(info.root), 0.5)
    assert result.root == Path(info.root)
    assert result.file_duration_s == 0.5
    assert result.channels[0].file_duration_s == 0.5


# ---------------------------------------------------------------------------
# Gaps (DECISIONS.md D12)
# ---------------------------------------------------------------------------


def test_no_gaps(make_recording):
    (ch,) = scan(make_recording())
    assert ch.gaps == ()


def test_one_missing_file(make_recording):
    (ch,) = scan(make_recording(gaps=frozenset({3})))
    assert ch.gaps == (Gap(start_unix=T0 + 3, missing_seconds=1.0),)


def test_consecutive_missing_files_are_one_gap(make_recording):
    (ch,) = scan(make_recording(gaps=frozenset({4, 5})))
    assert ch.gaps == (Gap(start_unix=T0 + 4, missing_seconds=2.0),)


def test_several_gaps_per_channel(make_recording):
    info = make_recording(
        n_channels=2,
        n_slots=30,
        gaps=frozenset({2}),
        channels={0: ChannelSpec(gaps=frozenset({10, 11, 12, 20})), 1: ChannelSpec()},
    )
    ch0, ch1 = scan(info)
    assert ch0.gaps == (
        Gap(start_unix=T0 + 2, missing_seconds=1.0),
        Gap(start_unix=T0 + 10, missing_seconds=3.0),
        Gap(start_unix=T0 + 20, missing_seconds=1.0),
    )
    assert ch1.gaps == (Gap(start_unix=T0 + 2, missing_seconds=1.0),)
    for ch, truth in zip((ch0, ch1), info.channels, strict=True):
        assert sum(g.missing_seconds for g in ch.gaps) == len(truth.missing)


def test_gaps_with_half_second_files(make_recording):
    info = make_recording(file_duration_s=0.5, gaps=frozenset({3, 4, 7}))
    (ch,) = scan(info)
    assert ch.gaps == (
        Gap(start_unix=T0 + 1.5, missing_seconds=1.0),
        Gap(start_unix=T0 + 3.5, missing_seconds=0.5),
    )


def test_jittered_timestamps(tmp_path):
    # Differences: 1.4 (jitter), 1.6 (one file), 1.5 (jitter), 2.5 and 3.5 (halves round up).
    stems = [
        "1790733600",
        "1790733601.4",
        "1790733603",
        "1790733604.5",
        "1790733607",
        "1790733610.5",
    ]
    write_files(tmp_path, [f"{s}.dat" for s in stems])
    (ch,) = scan_recording(tmp_path, 1.0).channels
    assert flat(ch.gaps) == pytest.approx([T0 + 2.4, 1.0, T0 + 5.5, 2.0, T0 + 8.0, 3.0])


def test_missing_files_outside_a_channel_span_are_not_gaps(make_recording):
    info = make_recording(n_slots=10, channels={0: ChannelSpec(first_slot=3, last_slot=6)})
    (ch,) = scan(info)
    assert ch.gaps == ()
    assert (ch.start_unix, ch.end_unix) == (T0 + 3, T0 + 7)


# ---------------------------------------------------------------------------
# Scale, progress, cancellation and the result type
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_50000_files_in_one_channel(make_recording):
    info = make_recording(n_slots=50_000, content="empty", gaps=frozenset({25_000}))
    (ch,) = scan(info)
    assert ch.n_files == 49_999
    assert (ch.start_unix, ch.end_unix) == (T0, T0 + 50_000)
    assert ch.gaps == (Gap(start_unix=T0 + 25_000, missing_seconds=1.0),)
    assert (ch.total_bytes, ch.sizes) == (0, frozenset({0}))


@pytest.mark.slow
def test_two_channels_of_20000_files(make_recording):
    info = make_recording(
        n_channels=2,
        n_slots=20_000,
        content="empty",
        channels={1: ChannelSpec(first_slot=100, gaps=frozenset(range(5000, 5100)))},
    )
    for ch, truth in zip(scan(info), info.channels, strict=True):
        assert_matches(ch, truth)


def test_no_stat_call_per_file(make_recording, monkeypatch):
    info = make_recording(n_channels=2, n_slots=300, content="empty")
    calls = []
    real_stat, real_lstat = os.stat, os.lstat

    def counting_stat(*args, **kwargs):
        calls.append(args[0])
        return real_stat(*args, **kwargs)

    def counting_lstat(*args, **kwargs):
        calls.append(args[0])
        return real_lstat(*args, **kwargs)

    monkeypatch.setattr(os, "stat", counting_stat)
    monkeypatch.setattr(os, "lstat", counting_lstat)
    channels = scan(info)
    monkeypatch.undo()
    assert sum(c.n_files for c in channels) == 600
    assert len(calls) <= 5


def test_progress_reports_the_total(make_recording):
    info = make_recording(n_channels=2, n_slots=1300, content="empty")
    seen: list[int] = []
    scan(info, progress=seen.append)
    assert seen == [PROGRESS_EVERY, 2 * PROGRESS_EVERY, 2600]


def test_cancel_before_the_first_folder(make_recording):
    info = make_recording()
    with pytest.raises(ScanCancelled):
        scan(info, cancelled=lambda: True)


def test_cancel_during_a_scan(make_recording):
    info = make_recording(n_channels=3, n_slots=1500, content="empty")
    checks = []

    def cancelled() -> bool:
        checks.append(1)
        return len(checks) > 3

    seen: list[int] = []
    with pytest.raises(ScanCancelled):
        scan(info, progress=seen.append, cancelled=cancelled)
    assert seen  # the scan was under way
    assert seen[-1] < 4500


@pytest.mark.parametrize("duration", [0.0, -1.0, float("nan"), float("inf")])
def test_file_duration_must_be_positive(tmp_path, duration):
    with pytest.raises(ValueError, match="file_duration_s"):
        scan_recording(tmp_path, duration)


def test_result_types_are_frozen(make_recording):
    result = scan_recording(Path(make_recording().root), 1.0)
    ch = result.channels[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.channels = ()  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        ch.files = ()  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        ch.files[0].size = 1  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        Gap(start_unix=0, missing_seconds=1).missing_seconds = 2  # type: ignore[misc]
