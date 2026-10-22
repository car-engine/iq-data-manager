"""The band list and the rule that picks a band for an fc (DECISIONS.md D88)."""

import itertools

import pytest

from iqdm.bands import BANDS, Band, band_for, band_named, bands_text


@pytest.mark.parametrize(
    ("fc_hz", "name"),
    [
        (2.999_999e6, None),
        (3e6, "HF"),
        (29.999_999e6, "HF"),
        (30e6, "VHF"),
        (145.8e6, "VHF"),
        (299.999_999e6, "VHF"),
        (300e6, "UHF"),
        (433e6, "UHF"),
        (999.999_999e6, "UHF"),
        (1e9, "L"),
        (1575.42e6, "L"),
        (2e9, "S"),
        (2.4e9, "S"),
        (4e9, "C"),
        (5.8e9, "C"),
        (8e9, "X"),
        (12e9, "Ku"),
        (14.25e9, "Ku"),
        (18e9, "K"),
        (27e9, "Ka"),
        (39.999e9, "Ka"),
        (40e9, None),
        (100e9, None),
    ],
)
def test_each_band_includes_its_lower_edge_and_not_its_upper(fc_hz, name):
    band = band_for(fc_hz)
    assert (None if band is None else band.name) == name


def test_the_list_runs_from_3_mhz_to_40_ghz_without_gaps_or_overlaps():
    for a, b in itertools.pairwise(BANDS):
        assert a.high_hz == b.low_hz, (a, b)
    assert (BANDS[0].low_hz, BANDS[-1].high_hz) == (3e6, 40e9)
    assert [b.name for b in BANDS] == ["HF", "VHF", "UHF", "L", "S", "C", "X", "Ku", "K", "Ka"]


def test_the_narrowest_band_wins_where_bands_overlap():
    marine = Band("Marine VHF", 156e6, 162.025e6)
    listed = (Band("VHF", 30e6, 300e6), marine)
    assert band_for(157e6, listed) is marine
    assert band_for(145.8e6, listed).name == "VHF"
    assert band_for(162.025e6, listed).name == "VHF"  # the upper edge is outside Marine VHF


def test_a_tie_goes_to_the_band_listed_first():
    first, second = Band("A", 1e6, 2e6), Band("B", 1e6, 2e6)
    assert band_for(1.5e6, (first, second)) is first
    assert band_for(1.5e6, (second, first)) is second


def test_names_match_without_letter_case():
    assert band_named(" uhf ").name == "UHF"
    assert band_named("KU").name == "Ku"
    assert band_named("Marine VHF") is None
    assert band_named("") is None


def test_range_text():
    texts = {b.name: b.range_text for b in BANDS}
    assert texts["HF"] == "3 to 30 MHz"
    assert texts["UHF"] == "300 to 1000 MHz"
    assert texts["L"] == "1 to 2 GHz"
    assert texts["Ka"] == "27 to 40 GHz"
    assert bands_text().startswith(
        "HF 3 to 30 MHz, VHF 30 to 300 MHz, UHF 300 to 1000 MHz, L 1 to 2 GHz"
    )
