"""Tests for iqdm.transfer.selection on synthetic recordings under tmp_path."""

from pathlib import Path

import pytest

from conftest import recording_from
from iqdm.models import Channel
from iqdm.scan.scanner import Gap, ScanCancelled, scan_recording
from iqdm.transfer.selection import (
    SelectionError,
    clip_gaps,
    in_range,
    select_files,
    select_from_scan,
)
from make_fixtures import ChannelSpec, format_stem

T0 = 1790733600.0  # 2026-09-30T02:00:00Z


def select(info, **kw):
    rec = recording_from(info)
    return select_from_scan(rec, scan_recording(Path(info.root), info.file_duration_s), **kw)


def stems(selection, channel_index=0) -> list[str]:
    (ch,) = [c for c in selection.channels if c.channel_index == channel_index]
    return [f.rel_path for f in ch.files]


def test_whole_recording_selects_every_file(make_recording):
    info = make_recording(n_channels=2, n_slots=5)
    sel = select(info)
    assert sel.is_whole
    assert sel.channel_indices is None
    assert sel.n_files == 10
    assert sel.total_bytes == sum(c.total_bytes for c in info.channels)
    assert stems(sel, 1) == [f"1/{format_stem(T0 + i)}.dat" for i in range(5)]
    assert sel.differences == ()
    assert sel.source == Path(info.root)


def test_files_carry_their_sizes(make_recording):
    info = make_recording(n_slots=3, wrong_size={2: 100})
    sizes = [f.size for f in select(info).files]
    assert sizes == [4000, 4000, 100]


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (T0 + 2, T0 + 5, [2, 3, 4]),  # the end is exclusive (D49)
        (T0 + 2.5, T0 + 5, [3, 4]),
        (T0 + 2, T0 + 5.01, [2, 3, 4, 5]),
        (None, T0 + 2, [0, 1]),
        (T0 + 8, None, [8, 9]),
    ],
)
def test_range_includes_start_and_excludes_end(make_recording, start, end, expected):
    info = make_recording(n_slots=10)
    sel = select(info, start_unix=start, end_unix=end)
    assert stems(sel) == [f"0/{format_stem(T0 + i)}.dat" for i in expected]
    assert not sel.is_whole
    assert (sel.range_start_unix, sel.range_end_unix) == (start, end)


def test_range_with_half_second_files(make_recording):
    info = make_recording(n_slots=10, file_duration_s=0.5, fs_hz=1000.0)
    sel = select(info, start_unix=T0 + 0.25, end_unix=T0 + 1.5)
    assert stems(sel) == [f"0/{format_stem(T0 + t)}.dat" for t in (0.5, 1.0)]


def test_range_with_fractional_timestamps(make_recording):
    info = make_recording(n_slots=4, start_unix=T0 + 0.25)
    sel = select(info, start_unix=T0 + 1.25, end_unix=T0 + 3.25)
    assert stems(sel) == ["0/1790733601.25.dat", "0/1790733602.25.dat"]


def test_range_outside_the_data_selects_nothing(make_recording):
    info = make_recording(n_slots=5)
    with pytest.raises(SelectionError, match="No files"):
        select(info, start_unix=T0 + 100, end_unix=T0 + 200)


@pytest.mark.parametrize("end", [T0 + 2, T0 + 1])
def test_end_must_be_after_start(make_recording, end):
    info = make_recording(n_slots=5)
    with pytest.raises(SelectionError, match="after its start"):
        select(info, start_unix=T0 + 2, end_unix=end)


def test_missing_seconds_are_the_gaps_inside_the_range(make_recording):
    info = make_recording(n_slots=20, gaps=frozenset({5, 6, 7}))
    whole = select(info)
    assert whole.channels[0].missing_seconds == 3.0
    part = select(info, start_unix=T0 + 6, end_unix=T0 + 12)
    assert part.channels[0].missing_seconds == 2.0
    assert part.channels[0].gaps == (Gap(start_unix=T0 + 6, missing_seconds=2.0),)
    assert stems(part) == [f"0/{format_stem(T0 + i)}.dat" for i in (8, 9, 10, 11)]


def test_time_outside_a_channels_files_is_not_missing(make_recording):
    info = make_recording(n_channels=2, n_slots=10, channels={1: ChannelSpec(first_slot=5)})
    sel = select(info, start_unix=T0, end_unix=T0 + 10)
    assert [c.missing_seconds for c in sel.channels] == [0.0, 0.0]
    assert sel.channels[1].n_files == 5


def test_channel_subset(make_recording):
    info = make_recording(n_channels=3, n_slots=4)
    sel = select(info, channels=[2, 1, 2])
    assert sel.channel_indices == (1, 2)
    assert [c.channel_index for c in sel.channels] == [1, 2]
    assert sel.n_files == 8
    assert not sel.is_whole


def test_a_subset_of_every_channel_is_the_whole_recording(make_recording):
    info = make_recording(n_channels=2, n_slots=4)
    sel = select(info, channels=[1, 0])
    assert sel.channel_indices is None
    assert sel.is_whole


def test_unknown_and_empty_channel_subsets(make_recording):
    info = make_recording(n_channels=2, n_slots=4)
    with pytest.raises(SelectionError, match="no channel 5"):
        select(info, channels=[0, 5])
    with pytest.raises(SelectionError, match="at least one channel"):
        select(info, channels=[])


def test_a_channel_missing_from_the_folder(make_recording):
    info = make_recording(n_channels=2, n_slots=4)
    rec = recording_from(info)
    rec.channels.append(
        Channel(channel_index=2, fc_hz=1.0, fs_hz=1.0, start_unix=T0, end_unix=T0 + 4, n_files=4)
    )
    scan = scan_recording(Path(info.root), 1.0)
    with pytest.raises(SelectionError, match="Channel 2 is not in the folder"):
        select_from_scan(rec, scan, channels=[2])
    sel = select_from_scan(rec, scan)
    assert sel.differences == ("Channel 2 is in the database but not in the folder.",)
    assert [c.channel_index for c in sel.channels] == [0, 1]


def test_differences_from_the_database_are_listed(make_recording):
    info = make_recording(n_slots=4)
    rec = recording_from(info)
    rec.channels[0].n_files = 3
    sel = select_from_scan(rec, scan_recording(Path(info.root), 1.0))
    assert sel.differences == ("Channel 0: the folder holds 4 files, the database lists 3.",)


def test_bin_files_keep_their_extension(make_recording):
    info = make_recording(n_slots=3, ext=".bin")
    assert stems(select(info)) == [f"0/{format_stem(T0 + i)}.bin" for i in range(3)]


def test_a_channel_with_both_extensions(make_recording):
    info = make_recording(n_slots=4, gaps=frozenset({2}))
    (Path(info.root) / "0" / f"{format_stem(T0 + 2)}.BIN").write_bytes(bytes(4000))
    assert stems(select(info)) == [
        f"0/{format_stem(T0)}.dat",
        f"0/{format_stem(T0 + 1)}.dat",
        f"0/{format_stem(T0 + 2)}.BIN",
        f"0/{format_stem(T0 + 3)}.dat",
    ]


def test_flat_recording_paths_have_no_folder(make_recording):
    info = make_recording(n_slots=2, flat=True)
    sel = select(info)
    assert sel.channels[0].sub_path == ""
    assert stems(sel) == [f"{format_stem(T0 + i)}.dat" for i in range(2)]


def test_unrecognised_files_are_not_selected(make_recording):
    info = make_recording(n_slots=3, junk=True)
    names = [f.rel_path for f in select(info).files]
    assert len(names) == 3
    assert all(n.endswith(".dat") and n.startswith("0/") for n in names)


def test_select_files_rescans_the_stored_folder(make_recording):
    info = make_recording(n_slots=3)
    rec = recording_from(info)
    assert select_files(rec).n_files == 3
    (Path(info.root) / "0" / f"{format_stem(T0 + 3)}.dat").write_bytes(bytes(4000))
    sel = select_files(rec)
    assert sel.n_files == 4
    assert sel.differences  # the database still lists 3 files


def test_select_files_takes_another_folder_and_can_be_cancelled(make_recording):
    info = make_recording(n_slots=3)
    rec = recording_from(info, storage_root="C:/nowhere")
    assert select_files(rec, folder=Path(info.root)).n_files == 3
    with pytest.raises(ScanCancelled):
        select_files(rec, folder=Path(info.root), cancelled=lambda: True)


@pytest.mark.parametrize(
    ("t", "start", "end", "inside"),
    [
        (5.0, 5.0, 6.0, True),
        (6.0, 5.0, 6.0, False),
        (4.999, 5.0, 6.0, False),
        (1e12, None, None, True),
        (5.0, None, 5.0, False),
    ],
)
def test_in_range(t, start, end, inside):
    assert in_range(t, start, end) is inside


def test_clip_gaps():
    gaps = [Gap(start_unix=10.0, missing_seconds=5.0), Gap(start_unix=30.0, missing_seconds=2.0)]
    assert clip_gaps(gaps, None, None) == tuple(gaps)
    assert clip_gaps(gaps, 12.0, 31.0) == (
        Gap(start_unix=12.0, missing_seconds=3.0),
        Gap(start_unix=30.0, missing_seconds=1.0),
    )
    assert clip_gaps(gaps, 15.0, 30.0) == ()
