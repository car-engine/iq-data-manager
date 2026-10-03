"""Tests for iqdm.legacy: the mapping rules of the legacy import (DECISIONS.md D66).

These tests build LegacyRow values directly and touch no file. The legacy database,
the new database and the command line are in test_migrate_legacy.py.
"""

from datetime import UTC, datetime

import pytest

from iqdm.db.legacy import LegacyRow
from iqdm.legacy import (
    LOGGED_BY,
    ImportPlan,
    Problem,
    build_plan,
    legacy_date_unix,
    parse_drive_map,
    report_text,
    split_data_dir,
)
from iqdm.models import ArchiveState, Endianness, IqLayout, SampleType

ROOT = "\\\\nas\\Data\\IQ"
NOW = "2026-10-04T08:00:00Z"
START = datetime(2026, 9, 18, 3, 0, tzinfo=UTC).timestamp()  # 11:00 at UTC+8
DATE = "2026-09-18 11:00:00"


def lrow(row: int = 1, **kw: object) -> LegacyRow:
    values: dict[str, object] = {
        "date": DATE,
        "date_unix": START,
        "site": "LocationA",
        "band": "VHF",
        "fc_hz": 145.8e6,
        "fs_hz": 1e6,
        "duration_s": 600,
        "data_dir": f"{ROOT}\\recording1\\0\\",
        "remarks": None,
    }
    values.update(kw)
    return LegacyRow(row=row, **values)


def plan_of(*rows: LegacyRow, drives: dict[str, str] | None = None) -> ImportPlan:
    return build_plan(rows, [ROOT], drives, now=NOW)


# =========================================================================
# Values
# =========================================================================


@pytest.mark.parametrize(
    ("data_dir", "expected"),
    [
        (f"{ROOT}\\recording1\\0\\", (f"{ROOT}\\recording1", 0, "0")),
        (f"{ROOT}\\recording1\\12", (f"{ROOT}\\recording1", 12, "12")),
        (f"{ROOT}\\recording1\\", (f"{ROOT}\\recording1", 0, "")),
        (f"{ROOT}\\recording1\\01\\", (f"{ROOT}\\recording1\\01", 0, "")),  # D11: leading zero
        ("//nas/Data/IQ/recording1/1/", (f"{ROOT}\\recording1", 1, "1")),
        (f"  {ROOT}\\recording1\\0  ", (f"{ROOT}\\recording1", 0, "0")),
    ],
)
def test_split_data_dir(data_dir, expected):
    assert split_data_dir(data_dir) == expected


@pytest.mark.parametrize(
    "text",
    [
        "2026-09-18 11:00:00",
        "2026-09-18T11:00:00",
        "2026/09/18 11:00:00",
        "2026-09-18 03:00:00+00:00",  # a text with its own offset keeps it
        " 2026-09-18 11:00 ",
    ],
)
def test_legacy_date_is_read_at_utc_plus_8(text):
    assert legacy_date_unix(text) == START


def test_legacy_date_keeps_a_fraction():
    assert legacy_date_unix("2026-09-18 11:00:00.5") == START + 0.5


@pytest.mark.parametrize("value", [None, "", "yesterday", "18/09/2026 11:00", 1789700400])
def test_legacy_date_that_cannot_be_read(value):
    assert legacy_date_unix(value) is None


def test_drive_map():
    assert parse_drive_map(["z:=\\\\nas\\Data", "Y: = \\\\nas\\Other"]) == {
        "Z:": "\\\\nas\\Data",
        "Y:": "\\\\nas\\Other",
    }
    assert parse_drive_map([]) == {}


@pytest.mark.parametrize("item", ["Z:", "Z=\\\\nas\\Data", "ZZ:=\\\\nas\\Data", "Z:=D:\\data"])
def test_wrong_drive_map(item):
    with pytest.raises(ValueError, match="Z:="):
        parse_drive_map([item])


# =========================================================================
# Recordings
# =========================================================================


def test_channel_rows_become_one_recording():
    plan = plan_of(
        lrow(1, data_dir=f"{ROOT}\\recording1\\1\\", fc_hz=433.92e6, band="UHF"),
        lrow(2),
    )
    assert plan.rejected == []
    assert plan.warnings == []
    assert plan.sites == ["LocationA"]
    [(site, rec)] = plan.recordings
    assert site == "LocationA"
    assert (rec.storage_root, rec.rel_path) == (ROOT, "recording1")
    assert [(c.channel_index, c.sub_path, c.band, c.fc_hz) for c in rec.channels] == [
        (0, "0", "VHF", 145.8e6),
        (1, "1", "UHF", 433.92e6),
    ]
    assert all((c.start_unix, c.end_unix) == (START, START + 600) for c in rec.channels)
    assert all(c.n_files is None and c.total_bytes is None for c in rec.channels)
    assert rec.logged_by == LOGGED_BY == "legacy-import"
    assert rec.archive_state is ArchiveState.ARCHIVED
    assert rec.archived_at == NOW
    assert rec.dtype is SampleType.INT16
    assert rec.iq_layout is IqLayout.INTERLEAVED_IQ
    assert rec.endianness is Endianness.LITTLE
    assert (rec.header_bytes, rec.file_duration_s) == (0, 1.0)
    assert rec.remarks is None


def test_a_folder_without_channel_folder_is_channel_0():
    [(_, rec)] = plan_of(lrow(data_dir=f"{ROOT}\\recording1")).recordings
    assert rec.rel_path == "recording1"
    assert [(c.channel_index, c.sub_path) for c in rec.channels] == [(0, "")]


def test_a_deeper_folder_keeps_its_relative_path():
    [(_, rec)] = plan_of(lrow(data_dir=f"{ROOT}\\2026\\LocationA\\rec7\\0")).recordings
    assert (rec.storage_root, rec.rel_path) == (ROOT, "2026\\LocationA\\rec7")


def test_rows_group_without_letter_case_and_keep_the_first_spelling():
    plan = plan_of(
        lrow(1, data_dir=f"{ROOT}\\Recording1\\0"),
        lrow(2, data_dir="\\\\NAS\\data\\iq\\RECORDING1\\1"),
    )
    [(_, rec)] = plan.recordings
    assert rec.rel_path == "Recording1"
    assert [c.channel_index for c in rec.channels] == [0, 1]


def test_a_mapped_drive_is_replaced_by_its_unc_path():
    plan = plan_of(lrow(data_dir="Z:\\IQ\\recording1\\0"), drives={"Z:": "\\\\nas\\Data"})
    [(_, rec)] = plan.recordings
    assert (rec.storage_root, rec.rel_path) == (ROOT, "recording1")


@pytest.mark.parametrize(
    ("data_dir", "reason"),
    [
        ("\\\\other\\share\\recording1\\0", "not under any NAS root"),
        ("D:\\data\\recording1\\0", "not under any NAS root"),
        ("Z:\\IQ\\recording1\\0", "not under any NAS root"),  # no --drive given
        (f"{ROOT}\\0", "NAS root cannot be a recording folder"),
        ("\\\\nas\\Data\\0", "share root cannot be a recording folder"),
        ("recording1\\0", "not an absolute path"),
        ("", "data_dir is empty"),
        (None, "data_dir is empty"),
    ],
)
def test_a_folder_that_cannot_be_mapped_is_reported(data_dir, reason):
    plan = plan_of(lrow(7, data_dir=data_dir))
    assert plan.recordings == []
    [problem] = plan.rejected
    assert problem.rows == (7,)
    assert reason in problem.text


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("fs_hz", 0, "fs_hz 0 is not a number above 0"),
        ("fs_hz", None, "fs_hz None is not a number above 0"),
        ("fc_hz", None, "fc_hz None is not a number"),
        ("fc_hz", "145.8", "fc_hz '145.8' is not a number"),
        ("duration_s", 0, "duration_s 0 is not a number above 0"),
        ("date_unix", "1789700400", "date_unix '1789700400' is not a number"),
        ("date_unix", float("nan"), "date_unix nan is not a number"),
        ("site", "  ", "site is empty"),
        ("site", None, "site is empty"),
    ],
)
def test_a_wrong_value_leaves_out_the_whole_recording(field, value, reason):
    plan = plan_of(lrow(1), lrow(2, data_dir=f"{ROOT}\\recording1\\1", **{field: value}))
    assert plan.recordings == []
    assert plan.sites == []
    [problem] = plan.rejected
    assert problem.rows == (1, 2)
    assert problem.text == f"{ROOT}\\recording1: row 2: {reason}"


def test_a_repeated_channel_is_reported():
    plan = plan_of(lrow(1), lrow(2), lrow(3, data_dir=f"{ROOT}\\recording1\\1"))
    assert plan.recordings == []
    [problem] = plan.rejected
    assert problem.rows == (1, 2, 3)
    assert problem.text.endswith("channel 0 appears in more than one row")


def test_two_rows_for_one_bare_folder_are_reported():
    plan = plan_of(lrow(1, data_dir=f"{ROOT}\\rec"), lrow(2, data_dir=f"{ROOT}\\rec\\"))
    [problem] = plan.rejected
    assert problem.text.endswith("channel 0 appears in more than one row")


def test_channel_folders_mixed_with_the_bare_folder_are_reported():
    plan = plan_of(
        lrow(1, data_dir=f"{ROOT}\\recording1"), lrow(2, data_dir=f"{ROOT}\\recording1\\1")
    )
    [problem] = plan.rejected
    assert problem.text.endswith("the rows mix channel folders with the recording folder itself")


def test_two_sites_in_one_recording_are_reported():
    plan = plan_of(lrow(1), lrow(2, data_dir=f"{ROOT}\\recording1\\1", site="LocationB"))
    [problem] = plan.rejected
    assert problem.text.endswith("the rows name different sites: LocationA, LocationB")


def test_one_site_in_two_spellings_within_a_recording_is_one_site():
    plan = plan_of(lrow(1), lrow(2, data_dir=f"{ROOT}\\recording1\\1", site="locationa"))
    assert plan.rejected == []
    assert plan.sites == ["LocationA"]


def test_site_spellings_merge_across_recordings():
    plan = plan_of(
        lrow(1, site="LocationA"),
        lrow(2, data_dir=f"{ROOT}\\recording2\\0", site="locationa"),
        lrow(3, data_dir=f"{ROOT}\\recording3\\0", site="LOCATIONA"),
        lrow(4, data_dir=f"{ROOT}\\recording4\\0", site="LocationB"),
    )
    assert plan.sites == ["LocationA", "LocationB"]
    assert [site for site, _ in plan.recordings] == ["LocationA"] * 3 + ["LocationB"]
    assert plan.site_spellings == {"LocationA": ["locationa", "LOCATIONA"]}


def test_sites_of_reported_recordings_are_not_written():
    plan = plan_of(lrow(1, site="LocationC", fs_hz=0), lrow(2, data_dir=f"{ROOT}\\rec2\\0"))
    assert plan.sites == ["LocationA"]


def test_different_remarks_are_joined_with_a_warning():
    plan = plan_of(
        lrow(1, remarks="antenna A"),
        lrow(2, data_dir=f"{ROOT}\\recording1\\1", remarks="antenna B"),
        lrow(3, data_dir=f"{ROOT}\\recording1\\2", remarks="antenna A"),
    )
    [(_, rec)] = plan.recordings
    assert rec.remarks == "antenna A | antenna B"
    assert plan.warnings == [Problem((1, 2, 3), f"{ROOT}\\recording1: remarks joined")]


def test_equal_remarks_are_kept_once():
    plan = plan_of(
        lrow(1, remarks=" calm day "),
        lrow(2, data_dir=f"{ROOT}\\recording1\\1", remarks="calm day"),
        lrow(3, data_dir=f"{ROOT}\\recording1\\2", remarks=""),
    )
    [(_, rec)] = plan.recordings
    assert rec.remarks == "calm day"
    assert plan.warnings == []


def test_date_unix_wins_over_a_different_date():
    plan = plan_of(lrow(4, date="2026-09-18 12:00:00"))
    [(_, rec)] = plan.recordings
    assert rec.channels[0].start_unix == START
    [warning] = plan.warnings
    assert warning.rows == (4,)
    assert "is +3600 s from date_unix" in warning.text
    assert warning.text.endswith("date_unix is used")


def test_a_date_within_one_second_gives_no_warning():
    assert plan_of(lrow(date_unix=START + 0.9)).warnings == []


def test_a_date_that_cannot_be_read_gives_a_warning():
    plan = plan_of(lrow(5, date="18/09/2026"))
    assert len(plan.recordings) == 1
    assert plan.warnings == [Problem((5,), "date '18/09/2026' cannot be read; date_unix is used")]


def test_channels_keep_their_own_times():
    plan = plan_of(
        lrow(1, duration_s=600),
        lrow(2, data_dir=f"{ROOT}\\recording1\\1", date_unix=START + 2, duration_s=300),
    )
    [(_, rec)] = plan.recordings
    assert [(c.start_unix, c.end_unix) for c in rec.channels] == [
        (START, START + 600),
        (START + 2, START + 302),
    ]


def test_problems_are_listed_in_row_order():
    plan = plan_of(
        lrow(9, data_dir="D:\\x\\0"),
        lrow(2, fs_hz=0),
        lrow(5, data_dir=""),
    )
    assert [p.rows for p in plan.rejected] == [(2,), (5,), (9,)]
    assert plan.rows_rejected == 3


def test_report_text():
    plan = plan_of(
        lrow(1, remarks="a"),
        lrow(2, data_dir=f"{ROOT}\\recording1\\1", remarks="b", date="x"),
        lrow(3, data_dir="D:\\x\\0"),
        lrow(4, data_dir=f"{ROOT}\\recording2", site="locationa"),
    )
    text = report_text(plan, legacy="old.db", new="new.db", table="log", now=NOW)
    lines = text.splitlines()
    assert lines[0] == f"Legacy import at {NOW}"
    assert "Legacy database: old.db (table log)" in lines
    assert "Rows read:         4" in lines
    assert "Recordings:        2 (3 channels)" in lines
    assert "Sites:             1" in lines
    assert "Rows not imported: 1" in lines
    assert "Warnings:          2" in lines
    assert "  row 3: D:\\x\\0: not under any NAS root given with --nas-root" in lines
    assert f"  rows 1, 2: {ROOT}\\recording1: remarks joined" in lines
    assert "  row 2: date 'x' cannot be read; date_unix is used" in lines
    assert "  LocationA (also written locationa)" in lines


def test_report_of_a_clean_import_has_no_lists():
    text = report_text(plan_of(lrow()), legacy="old.db", new="new.db", table="t", now=NOW)
    assert "Rows not imported:\n" not in text
    assert "Warnings (imported)" not in text
    assert "Site spellings" not in text
