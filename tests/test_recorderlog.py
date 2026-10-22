"""Values from the recording task's logs (DECISIONS.md D82).

The examples in tests/data/recorder are the user's two recordings of 2026-10-12, with
their folder paths and account name replaced. Other cases are written with
recorder_log_text() in the same format. Files live in tmp_path.
"""

import shutil
from pathlib import Path

import pytest

from conftest import RECORDER_EXAMPLES, recorder_log_text
from iqdm import recorderlog
from iqdm.entry import ItemState, ParamInput
from iqdm.models import SampleType
from iqdm.recorderlog import (
    FormValues,
    RecorderLog,
    checklist_items,
    form_values,
    merge_params,
    parse_command_line,
    parse_main_log,
    read_folder,
)
from iqdm.scan.scanner import scan_recording


def example(name: str, tmp_path: Path) -> Path:
    """A copy of an example's log files in a new folder under tmp_path."""
    folder = tmp_path / name
    shutil.copytree(RECORDER_EXAMPLES / name, folder)
    return folder


def read(folder: Path) -> RecorderLog:
    return read_folder(folder, sorted(p.name for p in folder.iterdir() if p.is_file()))


def test_the_one_channel_example(tmp_path):
    log = read(example("one_channel", tmp_path))
    assert log.files == ["recorder_one_channel.log", "log.txt", "check_quick.txt"]
    (ch,) = log.channels.values()
    assert (ch.index, ch.rate_hz, ch.freq_hz, ch.gain_db, ch.daughterboard) == (
        0,
        50e6,
        300e6,
        30.0,
        "UBX",
    )
    assert (log.sample_format, log.clock_source, log.time_source) == (
        "sc16",
        "internal",
        "internal",
    )
    assert log.pc_clock and log.gps_locked is None
    assert (log.mboard, log.files_written, log.restarts, log.verdict) == ("X310", 119, 0, "PASS")
    assert log.problems == []


def test_the_two_channel_example(tmp_path):
    log = read(example("two_channels", tmp_path))
    assert sorted(log.channels) == [0, 1]
    assert [c.freq_hz for c in log.channels.values()] == [300e6, 433e6]
    assert {c.gain_db for c in log.channels.values()} == {30.0}
    assert (log.clock_source, log.gps_locked, log.pc_clock) == ("gpsdo", True, False)
    assert (log.files_written, log.verdict) == (540, None)  # no check_quick.txt here


def test_form_values_of_the_two_channel_example(tmp_path):
    log = read(example("two_channels", tmp_path))
    values = form_values(log, [0, 1], [])
    assert values.dtype is SampleType.INT16
    assert values.fc_mhz == {0: "300", 1: "433"}
    assert values.fs_text == {0: "50 MHz", 1: "50 MHz"}
    assert [(p.channel_index, p.param, p.value, p.unit) for p in values.params] == [
        (None, "USRP gain", "30", "dB"),
        (None, "Clock reference", "GPSDO", ""),
        (None, "USRP", "X310 + UBX", ""),
    ]
    assert values.filled == (
        "sample type int16",
        "fc of channels 0, 1",
        "fs of channels 0, 1",
        "USRP gain",
        "Clock reference",
        "USRP",
    )


def test_a_usrp_row_already_in_the_form_stays():
    """The log cannot tell a USRP-2954 from an X310 with UBX boards."""
    log = RecorderLog(files=["x"])
    parse_main_log(recorder_log_text({0: (300.0, 30.0)}), log)
    rows = [ParamInput(param="usrp", value="USRP-2954")]
    values = form_values(log, [0], rows)
    assert "USRP" not in values.filled
    assert [p.param for p in values.params] == ["USRP gain", "Clock reference"]


def test_different_gains_give_a_row_per_channel():
    log = RecorderLog(files=["x"])
    parse_main_log(recorder_log_text({0: (300.0, 30.0), 2: (433.0, 31.5)}), log)
    values = form_values(log, [0, 2], [])
    gains = [(p.channel_index, p.value) for p in values.params if p.param == "USRP gain"]
    assert gains == [(0, "30"), (2, "31.5")]


def test_the_rows_take_the_catalogue_spelling():
    """Review of 1.1.0, finding 3: no line about a spelling the save would change."""
    log = RecorderLog(files=["x"])
    parse_main_log(recorder_log_text({0: (300.0, 30.0)}), log)
    values = form_values(log, [0], [], ["Antenna", "clock Reference", "USRP GAIN", "usrp"])
    assert [p.param for p in values.params] == ["USRP GAIN", "clock Reference", "usrp"]
    assert values.filled[-3:] == ("USRP GAIN", "clock Reference", "usrp")
    plain = form_values(log, [0], [], ["Antenna"])
    assert [p.param for p in plain.params] == ["USRP gain", "Clock reference", "USRP"]


def test_one_restart_is_one_time():
    log = RecorderLog(files=["x"], restarts=1)
    assert "The recorder restarted 1 time." in [i.text for i in checklist_items(log, None)]
    log.restarts = 2
    assert "The recorder restarted 2 times." in [i.text for i in checklist_items(log, None)]


def test_only_the_scanned_channels_are_filled():
    log = RecorderLog(files=["x"])
    parse_main_log(recorder_log_text({0: (300.0, 30.0), 1: (433.0, 30.0)}), log)
    values = form_values(log, [1], [])
    assert (values.fc_mhz, values.filled[1]) == ({1: "433"}, "fc of channel 1")


def test_four_twinrx_channels():
    """TwinRX records up to 4 channels; the board name drops its "RX0" suffix."""
    text = recorder_log_text(
        {0: (100.0, 20.0), 1: (200.0, 20.0), 2: (300.0, 20.0), 3: (400.0, 20.0)},
        subdev="TwinRX RX0",
    )
    log = RecorderLog(files=["x"])
    parse_main_log(text, log)
    assert sorted(log.channels) == [0, 1, 2, 3]
    values = form_values(log, [0, 1, 2, 3], [])
    assert values.fc_mhz == {0: "100", 1: "200", 2: "300", 3: "400"}
    assert ParamInput(param="USRP", value="X310 + TwinRX") in values.params


def test_a_channel_folder_named_after_the_usrp_channel():
    """Only channel 1 recorded: its folder is 1, and the log's channel 1 fills it."""
    log = RecorderLog(files=["x"])
    parse_main_log(recorder_log_text({1: (433.0, 30.0)}), log)
    assert sorted(log.channels) == [1]  # the other channels of the device summary go
    assert form_values(log, [1], []).fc_mhz == {1: "433"}


@pytest.mark.parametrize(
    ("fmt", "dtype"),
    [("sc16", SampleType.INT16), ("sc8", SampleType.INT8), ("fc32", SampleType.FLOAT32)],
)
def test_sample_formats(fmt, dtype):
    log = RecorderLog(files=["x"])
    parse_main_log(recorder_log_text({0: (1.0, 0.0)}, sample_format=fmt), log)
    assert form_values(log, [0], []).dtype is dtype


def test_an_unknown_sample_format_fills_no_sample_type():
    log = RecorderLog(files=["x"])
    parse_main_log(recorder_log_text({0: (1.0, 0.0)}, sample_format="sc12"), log)
    values = form_values(log, [0], [])
    assert values.dtype is None
    assert not any(f.startswith("sample type") for f in values.filled)


def test_the_command_line_alone(tmp_path):
    """log.txt only: requested values, with one gain for every channel."""
    folder = tmp_path / "rec"
    folder.mkdir()
    shutil.copy(RECORDER_EXAMPLES / "two_channels" / "log.txt", folder / "log.txt")
    log = read(folder)
    assert log.files == ["log.txt"]
    assert [(c.index, c.freq_hz, c.rate_hz, c.gain_db) for c in log.channels.values()] == [
        (0, 300e6, 50e6, 30.0),
        (1, 433e6, 50e6, 30.0),
    ]
    assert log.clock_source == "gpsdo"
    assert log.sample_format is None  # the command line does not name it


def test_the_main_log_wins_over_the_command_line():
    log = RecorderLog(files=["x"])
    parse_main_log(recorder_log_text({0: (300.5, 30.0)}), log)
    parse_command_line("--channels 0 --freq 300e6 --rate 2e6 --gain 10", log, fill_only=True)
    ch = log.channels[0]
    assert (ch.freq_hz, ch.gain_db, ch.rate_hz) == (300.5e6, 30.0, 1000.0)


def test_a_bad_command_line_is_a_problem():
    log = RecorderLog()
    parse_command_line("--channels 0 --freq lots", log)
    assert log.problems == ["the command line holds a value that is not a number"]


def test_several_logs_and_none_named_after_the_folder(tmp_path):
    folder = tmp_path / "rec"
    folder.mkdir()
    for name in ("recorder_a.log", "recorder_b.log"):
        (folder / name).write_text(recorder_log_text({0: (1.0, 0.0)}), encoding="utf-8")
    log = read(folder)
    assert not log.found
    assert log.problems == [
        "2 recorder logs and none named after the folder: recorder_a.log, recorder_b.log"
    ]
    assert "could not be used" in checklist_items(log, None)[0].text


def test_the_log_named_after_the_folder_is_used(tmp_path):
    folder = tmp_path / "rec"
    folder.mkdir()
    (folder / "recorder_old.log").write_text(recorder_log_text({0: (1.0, 0.0)}), "utf-8")
    (folder / "recorder_rec.log").write_text(recorder_log_text({0: (2.0, 0.0)}), "utf-8")
    assert read(folder).channels[0].freq_hz == 2e6


def test_a_log_too_large_is_not_read(tmp_path, monkeypatch):
    folder = example("one_channel", tmp_path)
    monkeypatch.setattr(recorderlog, "MAX_LOG_BYTES", 1000)  # log.txt is about 200 bytes
    log = read(folder)
    assert log.files == ["log.txt"]
    assert log.problems == [
        "recorder_one_channel.log is too large to read",
        "check_quick.txt is too large to read",
    ]
    assert log.channels[0].freq_hz == 300e6  # from the command line


def test_no_log_files_give_no_lines(make_recording):
    info = make_recording()
    log = read_folder(Path(info.root), [])
    assert not log.found
    assert checklist_items(log, None) == []
    assert form_values(log, [0], []) == FormValues()


def test_merge_replaces_every_row_of_a_name():
    current = [
        ParamInput(param="SDR", value="X310"),
        ParamInput(param="usrp gain", value="20", unit="dB", channel_index=0),
        ParamInput(param="USRP Gain", value="25", unit="dB", channel_index=1),
        ParamInput(param="Antenna", value="Yagi"),
    ]
    log_rows = [ParamInput(param="USRP Gain", value="30", unit="dB")]
    merged = merge_params(current, log_rows)
    assert [(p.param, p.value, p.channel_index) for p in merged] == [
        ("SDR", "X310", None),
        ("Antenna", "Yagi", None),
        ("USRP Gain", "30", None),
    ]


# ---------------------------------------------------------------------------
# Checklist lines
# ---------------------------------------------------------------------------


def lines(log: RecorderLog, scan=None, filled=()) -> list[tuple[ItemState, str]]:
    return [(i.state, i.text) for i in checklist_items(log, scan, filled)]


def test_lines_of_the_one_channel_example(tmp_path):
    log = read(example("one_channel", tmp_path))
    got = lines(log, filled=("USRP Gain",))
    assert got[0] == (
        ItemState.INFO,
        "Filled in from the recorder's log: USRP Gain. Check them against the recording task.",
    )
    assert (ItemState.OK, "The recorder's own check passed") in got
    assert any("from the PC clock, not from GPS" in text for _, text in got)


def test_no_line_blocks_saving():
    log = RecorderLog(
        files=["x"],
        verdict="FAIL",
        pc_clock=True,
        gps_locked=False,
        restarts=2,
        stop_reason="error",
        problems=["cannot read x"],
    )
    states = {state for state, _ in lines(log)}
    assert states <= {ItemState.INFO, ItemState.OK}


def test_the_file_count_differs(make_recording, tmp_path):
    info = make_recording(n_channels=2, n_slots=5)
    scan = scan_recording(Path(info.root), 1.0)
    log = RecorderLog(files=["x"], files_written=12)
    assert lines(log, scan) == [
        (
            ItemState.INFO,
            "The recorder wrote 12 files; the folder holds 10. "
            "2 files went missing after recording.",
        )
    ]
    assert lines(RecorderLog(files=["x"], files_written=10), scan) == []
    assert lines(RecorderLog(files=["x"], files_written=9), scan) == [
        (ItemState.INFO, "The recorder wrote 9 files; the folder holds 10.")
    ]
