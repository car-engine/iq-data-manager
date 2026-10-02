"""Tests for iqdm.transfer.estimate."""

import pytest

from iqdm.transfer.estimate import duration_text, estimate


def test_copy_time_at_the_network_speed():
    e = estimate(bytes_to_copy=1_100_000_000, hashed_bytes=0, speed_mb_s=110)
    assert e.copy_s == pytest.approx(10.0)
    assert e.hash_s == 0
    assert e.total_s == pytest.approx(10.0)


def test_one_terabyte_at_110_mb_s_takes_about_two_and_a_half_hours():
    e = estimate(bytes_to_copy=10**12, hashed_bytes=0, speed_mb_s=110)
    assert duration_text(e.total_s) == "about 2 h 32 min"


def test_hash_time_reads_hashed_and_resumed_bytes():
    e = estimate(
        bytes_to_copy=0, hashed_bytes=220_000_000, speed_mb_s=110, rehashed_source_bytes=110_000_000
    )
    assert e.hash_s == pytest.approx(3.0)


def test_nothing_to_copy_takes_no_time():
    assert estimate(bytes_to_copy=0, hashed_bytes=0, speed_mb_s=110).total_s == 0


@pytest.mark.parametrize("speed", [0, -1])
def test_speed_must_be_positive(speed):
    with pytest.raises(ValueError, match="positive"):
        estimate(bytes_to_copy=1, hashed_bytes=0, speed_mb_s=speed)


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "under a minute"),
        (59.9, "under a minute"),
        (60, "about 1 min"),
        (61, "about 2 min"),
        (3599, "about 1 h"),
        (3600, "about 1 h"),
        (9000, "about 2 h 30 min"),
    ],
)
def test_duration_text(seconds, text):
    assert duration_text(seconds) == text
