"""Tests for tools/make_fixtures.py. Every file is created under tmp_path."""

import array
import json
import sys
from pathlib import Path

import pytest

import make_fixtures as mf
from make_fixtures import ChannelSpec, RecordingSpec

START = mf.DEFAULT_START_UNIX


def data_files(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.is_file())


def test_default_recording(make_recording):
    info = make_recording()
    root = Path(info.root)
    assert [p.name for p in root.iterdir()] == ["0"]
    names = data_files(root / "0")
    assert names == [f"{START + i}.dat" for i in range(10)]
    assert {(root / "0" / n).stat().st_size for n in names} == {4000}

    (ch,) = info.channels
    assert ch.sub_path == "0"
    assert ch.n_files == 10
    assert ch.total_bytes == 40_000
    assert ch.expected_file_bytes == ch.file_bytes == 4000
    assert ch.start_unix == START
    assert ch.end_unix == START + 10  # exclusive
    assert ch.missing == []


def test_flat_layout_puts_files_in_recording_folder(make_recording):
    info = make_recording(flat=True, n_slots=3)
    root = Path(info.root)
    assert data_files(root) == [f"{START + i}.dat" for i in range(3)]
    assert info.channels[0].sub_path == ""


def test_flat_layout_needs_one_channel(make_recording):
    with pytest.raises(mf.SpecError, match="exactly one channel"):
        make_recording(flat=True, n_channels=2)


def test_three_channels_use_numbered_subfolders(make_recording):
    info = make_recording(n_channels=3, n_slots=4)
    root = Path(info.root)
    assert sorted(p.name for p in root.iterdir()) == ["0", "1", "2"]
    for ch in info.channels:
        assert len(data_files(root / ch.sub_path)) == 4


def test_gaps_in_all_channels_and_one_channel(make_recording):
    spec = RecordingSpec(
        n_channels=2,
        gaps=frozenset({3, 4}),
        channels={1: ChannelSpec(gaps=frozenset({7}))},
    )
    info = make_recording(spec)
    root = Path(info.root)
    ch0, ch1 = info.channels
    assert ch0.missing == [START + 3, START + 4]
    assert ch1.missing == [START + 3, START + 4, START + 7]
    assert ch0.n_files == 8
    assert ch1.n_files == 7
    assert f"{START + 7}.dat" in data_files(root / "0")
    assert f"{START + 7}.dat" not in data_files(root / "1")


def test_edge_gap_moves_start_and_is_not_missing(make_recording):
    info = make_recording(gaps=frozenset({0, 9}))
    ch = info.channels[0]
    assert ch.start_unix == START + 1
    assert ch.end_unix == START + 9
    assert ch.missing == []


def test_channel_span(make_recording):
    spec = RecordingSpec(n_channels=2, channels={1: ChannelSpec(first_slot=2, last_slot=5)})
    info = make_recording(spec)
    ch1 = info.channels[1]
    assert ch1.timestamps == [START + s for s in range(2, 6)]
    assert ch1.start_unix == START + 2
    assert ch1.end_unix == START + 6
    assert info.channels[0].n_files == 10


def test_header_bytes_add_to_size_and_start_with_magic(make_recording):
    info = make_recording(header_bytes=64, n_slots=1)
    path = Path(info.root) / "0" / f"{START}.dat"
    data = path.read_bytes()
    assert len(data) == 64 + 4000
    assert data[:8] == mf.HEADER_MAGIC
    assert data[8:64] == bytes(56)
    assert info.channels[0].expected_file_bytes == 4064


def test_short_header_is_truncated_magic(make_recording):
    info = make_recording(header_bytes=4, n_slots=1)
    data = (Path(info.root) / "0" / f"{START}.dat").read_bytes()
    assert data[:4] == mf.HEADER_MAGIC[:4]
    assert len(data) == 4004


def test_wrong_size_default_is_half(make_recording):
    info = make_recording(wrong_size={3: None})
    path = Path(info.root) / "0" / f"{START + 3}.dat"
    assert path.stat().st_size == 2000
    assert info.channels[0].wrong_size == {f"{START + 3}.dat": 2000}
    assert info.channels[0].total_bytes == 9 * 4000 + 2000


def test_wrong_size_explicit_larger_is_zero_padded(make_recording):
    spec = RecordingSpec(n_channels=2, channels={1: ChannelSpec(wrong_size={0: 4100})})
    info = make_recording(spec)
    path = Path(info.root) / "1" / f"{START}.dat"
    assert path.stat().st_size == 4100
    assert path.read_bytes()[4000:] == bytes(100)
    assert info.channels[0].wrong_size == {}


def test_wrong_size_on_a_gap_is_rejected(make_recording):
    with pytest.raises(mf.SpecError, match="has no file"):
        make_recording(gaps=frozenset({2}), wrong_size={2: None})


@pytest.mark.parametrize(
    ("dtype", "size"), [("int8", 2000), ("int16", 4000), ("int32", 8000), ("float32", 8000)]
)
def test_file_size_per_dtype(make_recording, dtype, size):
    info = make_recording(dtype=dtype, n_slots=1)
    assert (Path(info.root) / "0" / f"{START}.dat").stat().st_size == size
    assert info.channels[0].expected_file_bytes == size


def test_fractional_file_duration(make_recording):
    info = make_recording(file_duration_s=0.5, n_slots=4)
    names = data_files(Path(info.root) / "0")
    assert names == sorted(
        [f"{START}.dat", f"{START}.5.dat", f"{START + 1}.dat", f"{START + 1}.5.dat"]
    )
    assert info.channels[0].timestamps == [START, START + 0.5, START + 1, START + 1.5]
    assert info.channels[0].expected_file_bytes == 2000
    assert info.channels[0].end_unix == START + 2


def test_non_whole_sample_count_is_rejected(make_recording):
    with pytest.raises(mf.SpecError, match="whole number of samples"):
        make_recording(fs_hz=1001, file_duration_s=0.5)


def test_empty_content_writes_zero_byte_files(make_recording):
    info = make_recording(content="empty", n_slots=500)
    folder = Path(info.root) / "0"
    assert len(data_files(folder)) == 500
    assert {p.stat().st_size for p in folder.iterdir()} == {0}
    ch = info.channels[0]
    assert ch.file_bytes == 0
    assert ch.total_bytes == 0
    assert ch.expected_file_bytes == 4000


def test_zeros_content(make_recording):
    info = make_recording(content="zeros", n_slots=1, header_bytes=8)
    data = (Path(info.root) / "0" / f"{START}.dat").read_bytes()
    assert data[8:] == bytes(4000)


def test_random_content_keeps_the_header_and_size(make_recording):
    info = make_recording(content="random", n_slots=2, header_bytes=8)
    first, second = ((Path(info.root) / "0" / f"{START + i}.dat").read_bytes() for i in range(2))
    assert len(first) == len(second) == 4008
    assert first[:8] == second[:8]  # the same header
    assert first[8:] != second[8:]
    assert first[8:] != bytes(4000)


def test_bin_extension(make_recording):
    info = make_recording(ext=".bin", n_slots=2)
    assert data_files(Path(info.root) / "0") == [f"{START}.bin", f"{START + 1}.bin"]


def test_junk_files_are_listed(make_recording):
    info = make_recording(junk=True, n_slots=2)
    root = Path(info.root)
    assert info.unrecognised == ["notes.txt", "README", f"0/{START}.tmp", "0/abc.dat"]
    for rel in info.unrecognised:
        assert (root / rel).is_file()


def test_junk_files_in_flat_layout(make_recording):
    info = make_recording(junk=True, flat=True, n_slots=2)
    assert info.unrecognised == ["notes.txt", "README", f"{START}.tmp", "abc.dat"]


def test_tone_decodes_as_interleaved_int16_little_endian(make_recording):
    info = make_recording(n_slots=2)
    folder = Path(info.root) / "0"
    samples = array.array("h", (folder / f"{START}.dat").read_bytes())
    if sys.byteorder != "little":
        samples.byteswap()
    amplitude = round(mf.TONE_AMPLITUDE * 32767)
    assert samples[0] == amplitude  # I at n = 0
    assert samples[1] == 0  # Q at n = 0
    assert max(samples) == amplitude
    # Channel 0 tone is fs / 16: a quarter period later, I = 0 and Q = amplitude.
    assert samples[2 * 4] == 0
    assert samples[2 * 4 + 1] == amplitude


def test_tone_is_continuous_across_files(make_recording):
    # 1000 samples per file is not a multiple of the 16-sample period, so the second
    # file must start at phase 1000 % 16 = 8: I = -amplitude, Q = 0.
    info = make_recording(n_slots=2)
    data = (Path(info.root) / "0" / f"{START + 1}.dat").read_bytes()
    samples = array.array("h", data)
    if sys.byteorder != "little":
        samples.byteswap()
    amplitude = round(mf.TONE_AMPLITUDE * 32767)
    assert samples[0] == -amplitude
    assert samples[1] == 0


def test_channels_have_different_tones(make_recording):
    info = make_recording(n_channels=2, n_slots=1)
    root = Path(info.root)
    a = (root / "0" / f"{START}.dat").read_bytes()
    b = (root / "1" / f"{START}.dat").read_bytes()
    assert a != b


def test_refuses_non_empty_folder(tmp_path):
    out = tmp_path / "rec"
    out.mkdir()
    (out / "existing.txt").write_text("keep me")
    with pytest.raises(mf.OutputRefusedError, match="not empty"):
        mf.make_recording(out, RecordingSpec())
    assert [p.name for p in out.iterdir()] == ["existing.txt"]
    assert (out / "existing.txt").read_text() == "keep me"


def test_accepts_existing_empty_folder(tmp_path):
    out = tmp_path / "rec"
    out.mkdir()
    info = mf.make_recording(out, RecordingSpec(n_slots=1))
    assert info.channels[0].n_files == 1


def test_refuses_output_that_is_a_file(tmp_path):
    out = tmp_path / "rec"
    out.write_text("x")
    with pytest.raises(mf.OutputRefusedError, match="not a folder"):
        mf.make_recording(out, RecordingSpec())


@pytest.mark.parametrize("raw", [r"\\server\share\rec", "//server/share/rec"])
def test_refuses_network_path_before_touching_it(raw):
    with pytest.raises(mf.OutputRefusedError, match="network paths"):
        mf._check_output_dir(Path(raw))


def test_refuses_filesystem_root(tmp_path):
    root = Path(tmp_path.anchor)
    with pytest.raises(mf.OutputRefusedError, match="root"):
        mf._check_output_dir(root)


def test_spec_is_validated_before_anything_is_written(tmp_path):
    out = tmp_path / "rec"
    with pytest.raises(mf.SpecError):
        mf.make_recording(out, RecordingSpec(dtype="int12"))
    assert not out.exists()


def test_format_stem():
    assert mf.format_stem(1790733600.0) == "1790733600"
    assert mf.format_stem(1790733600.5) == "1790733600.5"
    assert mf.format_stem(1790733600.25) == "1790733600.25"


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def test_cli_json_round_trip(tmp_path, capsys):
    out = tmp_path / "demo"
    code = mf.main(
        [
            str(out),
            "--channels",
            "2",
            "--files",
            "6",
            "--gap",
            "2-3",
            "--gap",
            "1:5",
            "--span",
            "0:0-4",
            "--wrong-size",
            "1:1=10",
            "--header-bytes",
            "16",
            "--junk",
            "--json",
        ]
    )
    assert code == 0
    info = json.loads(capsys.readouterr().out)
    ch0, ch1 = info["channels"]

    assert ch0["timestamps"] == [START, START + 1, START + 4]
    assert ch0["missing"] == [START + 2, START + 3]
    assert ch1["timestamps"] == [START, START + 1, START + 4]  # slot 5 gapped at the end
    assert ch1["wrong_size"] == {f"{START + 1}.dat": 10}
    assert ch0["expected_file_bytes"] == 4016
    assert len(info["unrecognised"]) == 4

    for ch in (ch0, ch1):
        folder = out / ch["sub_path"]
        names = sorted(p.name for p in folder.iterdir() if p.suffix == ".dat")
        expected = sorted(f"{mf.format_stem(t)}.dat" for t in ch["timestamps"])
        if ch["sub_path"] == "0":
            expected = sorted([*expected, "abc.dat"])
        assert names == expected
        sizes = sum((folder / f"{mf.format_stem(t)}.dat").stat().st_size for t in ch["timestamps"])
        assert sizes == ch["total_bytes"]


def test_cli_summary_output(tmp_path, capsys):
    assert mf.main([str(tmp_path / "demo"), "--files", "5", "--gap", "2"]) == 0
    out = capsys.readouterr().out
    assert "channel 0 0/: 4 files, 16000 bytes" in out
    assert f"missing: {START + 2}" in out


@pytest.mark.parametrize("bad", ["x", "1:", "3-1", "a:2", "1:2:3"])
def test_cli_bad_gap_is_usage_error(tmp_path, bad):
    with pytest.raises(SystemExit) as exc:
        mf.main([str(tmp_path / "demo"), "--gap", bad])
    assert exc.value.code == 2
    assert not (tmp_path / "demo").exists()


def test_cli_invalid_spec_is_usage_error(tmp_path):
    with pytest.raises(SystemExit) as exc:
        mf.main([str(tmp_path / "demo"), "--flat", "--channels", "2"])
    assert exc.value.code == 2


def test_cli_refused_output_exits_one(tmp_path, capsys):
    out = tmp_path / "demo"
    out.mkdir()
    (out / "keep.dat").write_bytes(b"x")
    assert mf.main([str(out)]) == 1
    assert "refused" in capsys.readouterr().err
    assert (out / "keep.dat").read_bytes() == b"x"
