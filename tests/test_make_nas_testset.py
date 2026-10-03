"""Tests for tools/make_nas_testset.py. Every test set is written under tmp_path."""

import json
from pathlib import Path

import pytest

import make_nas_testset as testset
from conftest import recording_from
from iqdm.scan.scanner import check_channel, scan_recording
from iqdm.transfer.selection import select_from_scan

TINY = testset.SetSizes(
    large_files=3,
    large_file_bytes=8_000,
    small_files=20,
    small_file_bytes=400,
    mid_files=60,
    mid_file_bytes=1_000,
)

FOLDERS = [
    "A-large-files",
    "B-small-files",
    "C-gaps-and-ranges",
    "D-bin-single-channel",
    "E-half-second-files",
]


@pytest.fixture
def made(tmp_path):
    out = tmp_path / "set"
    infos = testset.make_testset(out, TINY)
    return out, infos


def test_every_recording_is_written_with_a_readme_and_ground_truth(made):
    out, infos = made
    assert sorted(p.name for p in out.iterdir()) == [*FOLDERS, "TESTSET.md", "testset.json"]
    truth = json.loads((out / "testset.json").read_text(encoding="utf-8"))
    assert list(truth) == FOLDERS
    readme = (out / "TESTSET.md").read_text(encoding="utf-8")
    for folder in FOLDERS:
        assert f"`{folder}`" in readme
    assert "scratch database" in readme
    assert len(infos) == 5


def test_each_recording_scans_cleanly(made):
    out, infos = made
    for folder, info in zip(FOLDERS, infos, strict=True):
        scan = scan_recording(out / folder, info.file_duration_s)
        assert [c.n_files for c in scan.channels] == [c.n_files for c in info.channels]
        assert scan.unrecognised == ()
        for ch, truth in zip(scan.channels, info.channels, strict=True):
            findings = check_channel(
                ch, fs_hz=info.fs_hz, dtype=info.dtype, header_bytes=info.header_bytes
            )
            assert all(f.severity == "info" for f in findings), (folder, findings)
            assert ch.total_bytes == truth.total_bytes


def test_the_cases_each_recording_covers(made):
    out, infos = made
    a, b, c, d, e = infos
    assert a.channels[0].file_bytes == 8_000
    assert b.channels[0].n_files == 20
    assert b.channels[0].file_bytes == 400
    assert c.channels[0].missing  # gaps in channel 0
    assert c.channels[1].start_unix > c.channels[0].start_unix  # channel 1 starts later
    assert d.channels[0].sub_path == ""
    assert all(p.suffix == ".bin" for p in (out / FOLDERS[3]).iterdir())
    assert d.channels[0].wrong_size  # a short last file
    assert e.file_duration_s == 0.5
    assert any(not float(t).is_integer() for t in e.channels[0].timestamps)
    starts = [info.channels[0].start_unix for info in infos]
    assert len(set(starts)) == 5  # each recording is its own capture


def test_files_hold_random_bytes(made):
    out, _ = made
    first = out / "A-large-files" / "0" / "1790733600.dat"
    second = out / "A-large-files" / "0" / "1790733601.dat"
    assert first.read_bytes() != second.read_bytes()
    assert first.read_bytes() != bytes(8_000)


def test_a_range_of_the_gaps_recording_has_missing_seconds(made):
    out, infos = made
    c = infos[2]
    rec = recording_from(c)
    sel = select_from_scan(
        rec,
        scan_recording(out / "C-gaps-and-ranges", 1.0),
        start_unix=c.channels[0].start_unix + 5,
        end_unix=c.channels[0].start_unix + 25,
    )
    assert sel.channels[0].missing_seconds == 10.0


def expected_total(sizes) -> int:
    """Bytes of the set, from its specs, without writing it."""
    total = 0
    for rec in testset.recordings(sizes):
        spec = rec.spec
        file_bytes = round(spec.fs_hz * spec.file_duration_s) * 4
        for ch in range(spec.n_channels):
            ch_spec = spec.channels.get(ch)
            first = ch_spec.first_slot if ch_spec else 0
            gaps = (ch_spec.gaps if ch_spec else frozenset()) | spec.gaps
            n = spec.n_slots - first - len(gaps)
            short = sum(file_bytes - file_bytes // 2 for _ in spec.wrong_size)
            total += n * file_bytes - short
    return total


def test_default_sizes_match_the_documented_total():
    sizes = testset.SetSizes()
    specs = {r.folder: r.spec for r in testset.recordings(sizes)}
    assert specs["A-large-files"].fs_hz == 50e6
    assert specs["B-small-files"].fs_hz == 16e3
    assert specs["C-gaps-and-ranges"].fs_hz == 250e3
    assert expected_total(sizes) == 5_054_500_000  # "5.05 GB" in the tool's text


def test_quick_sizes_match_the_documented_total(made, tmp_path):
    assert expected_total(TINY) == sum(c.total_bytes for info in made[1] for c in info.channels)
    assert round(expected_total(testset.QUICK) / 1e5) / 10 == 67.8


def test_a_used_folder_is_refused(tmp_path, capsys):
    out = tmp_path / "set"
    out.mkdir()
    (out / "x.txt").write_text("x", encoding="utf-8")
    assert testset.main([str(out), "--quick"]) == 1
    assert "new or empty" in capsys.readouterr().err
    assert sorted(p.name for p in out.iterdir()) == ["x.txt"]


@pytest.mark.parametrize("argv", [["--large-files", "0"], ["--large-mb", "0.000001"]])
def test_wrong_sizes_are_refused(tmp_path, capsys, argv):
    assert testset.main([str(tmp_path / "set"), "--quick", *argv]) == 2
    assert not (tmp_path / "set").exists()


def test_quick_set_from_the_command_line(tmp_path, capsys):
    out = tmp_path / "set"
    assert testset.main([str(out), "--quick", "--small-files", "10"]) == 0
    printed = capsys.readouterr().out
    assert "Done: 5 recordings" in printed
    truth = json.loads((out / "testset.json").read_text(encoding="utf-8"))
    assert [c["n_files"] for c in truth["B-small-files"]["channels"]] == [10, 10]
    assert Path(truth["A-large-files"]["root"]).name == "A-large-files"
