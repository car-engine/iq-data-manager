"""Tests for iqdm.timeutil and iqdm.models."""

import re
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from importlib import resources

import pytest

from iqdm import models, timeutil
from iqdm.models import Channel
from iqdm.timeutil import iso_to_unix, unix_to_iso, utc_now_iso

SCHEMA = resources.files("iqdm.db").joinpath("schema.sql").read_text(encoding="utf-8")


def schema_check_values(column: str) -> set[str]:
    """Quoted values in the schema's `CHECK (column IN (...))` clause."""
    start = SCHEMA.index(f"CHECK ({column} IN (")
    end = SCHEMA.index("))", start)
    return set(re.findall(r"'([^']+)'", SCHEMA[start:end]))


# ---------------------------------------------------------------------------
# timeutil
# ---------------------------------------------------------------------------


def test_unix_to_iso():
    assert unix_to_iso(1790733600) == "2026-09-30T02:00:00Z"
    assert unix_to_iso(1790733600.9) == "2026-09-30T02:00:00Z"
    assert unix_to_iso(0) == "1970-01-01T00:00:00Z"


def test_iso_round_trip():
    assert iso_to_unix("2026-09-30T02:00:00Z") == 1790733600.0
    assert iso_to_unix(unix_to_iso(1790733601)) == 1790733601.0


@pytest.mark.parametrize(
    "text", ["2026-09-30T02:00:00", "2026-09-30T02:00:00+00:00", "2026-09-30 02:00:00Z", ""]
)
def test_iso_to_unix_rejects_other_forms(text):
    with pytest.raises(ValueError, match="expected"):
        iso_to_unix(text)


def test_utc_now_iso_converts_to_utc():
    plus8 = timezone(timedelta(hours=8))
    assert utc_now_iso(datetime(2026, 10, 2, 10, 0, 0, tzinfo=plus8)) == "2026-10-02T02:00:00Z"


def test_utc_now_iso_rejects_naive():
    with pytest.raises(ValueError, match="timezone-aware"):
        utc_now_iso(datetime(2026, 10, 2))  # noqa: DTZ001


def test_utc_now_iso_default_is_now():
    before = datetime.now(UTC).replace(microsecond=0)
    stamp = iso_to_unix(utc_now_iso())
    assert before.timestamp() <= stamp <= before.timestamp() + 5


# ---------------------------------------------------------------------------
# Enums match schema.sql
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "enum"),
    [
        ("dtype", models.SampleType),
        ("iq_layout", models.IqLayout),
        ("endianness", models.Endianness),
        ("archive_state", models.ArchiveState),
        ("operation", models.Operation),
        ("verification", models.Verification),
        ("hash_mode", models.HashMode),
    ],
)
def test_enum_matches_schema(column: str, enum: type[StrEnum]):
    assert {e.value for e in enum} == schema_check_values(column)


def test_bytes_per_sample_covers_every_sample_type():
    assert set(models.BYTES_PER_SAMPLE) == set(models.SampleType)
    assert models.BYTES_PER_SAMPLE[models.SampleType.INT16] == 2


# ---------------------------------------------------------------------------
# Coverage and envelope
# ---------------------------------------------------------------------------


def ch(start=0.0, end=10.0, n_files=10, index=0) -> Channel:
    return Channel(
        channel_index=index, fc_hz=1e8, fs_hz=1e3, start_unix=start, end_unix=end,
        n_files=n_files,
    )


def test_channel_coverage():
    assert models.channel_coverage(ch(n_files=10), 1.0) == 1.0
    assert models.channel_coverage(ch(n_files=8), 1.0) == 0.8
    assert models.channel_coverage(ch(end=5.0, n_files=10), 0.5) == 1.0


def test_channel_coverage_undefined():
    assert models.channel_coverage(ch(n_files=None), 1.0) is None
    assert models.channel_coverage(ch(start=5.0, end=5.0, n_files=0), 1.0) is None


def test_recording_coverage_is_minimum():
    assert models.recording_coverage([ch(n_files=10), ch(n_files=9, index=1)], 1.0) == 0.9


def test_recording_coverage_none_if_any_undefined_or_empty():
    assert models.recording_coverage([ch(), ch(n_files=None, index=1)], 1.0) is None
    assert models.recording_coverage([], 1.0) is None


def test_envelope():
    assert models.envelope([ch(start=2, end=8), ch(start=0, end=6, index=1)]) == (0, 8)
    with pytest.raises(ValueError, match="at least one channel"):
        models.envelope([])


@pytest.mark.parametrize(
    ("hours", "label"),
    [(0, "UTC"), (8, "UTC+8"), (5.5, "UTC+5:30"), (-3.5, "UTC-3:30"), (12.75, "UTC+12:45")],
)
def test_offset_label(hours, label):
    assert timeutil.offset_label(hours) == label


def test_display_time_uses_the_offset_and_ignores_the_pc_time_zone():
    t = 1790733600.9  # 2026-09-30T02:00:00.9Z
    assert timeutil.display_time(t, 0) == "2026-09-30 02:00:00"
    assert timeutil.display_time(t, 8) == "2026-09-30 10:00:00"
    assert timeutil.display_time(t, -3.5) == "2026-09-29 22:30:00"
    assert timeutil.display_time(1790784000, 8) == "2026-10-01 00:00:00"  # crosses midnight
