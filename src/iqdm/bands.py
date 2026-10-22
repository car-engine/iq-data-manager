"""Frequency bands for the Log tab's band box (DECISIONS.md D88).

The names and edges follow IEEE Std 521: HF, VHF and UHF up to 1 GHz, then the letter
bands L to Ka. Every PC on the same version uses the same list; a change comes with a
new release. Each band includes its lower edge and excludes its upper edge. Where
bands overlap, the narrowest band that contains fc wins, and a tie goes to the band
listed first. The list below has no overlaps; the rule is there for a later band such
as Marine VHF inside VHF.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Band:
    """A named frequency range: low_hz is in the band, high_hz is not."""

    name: str
    low_hz: float
    high_hz: float

    def contains(self, fc_hz: float) -> bool:
        return self.low_hz <= fc_hz < self.high_hz

    @property
    def width_hz(self) -> float:
        return self.high_hz - self.low_hz

    @property
    def range_text(self) -> str:
        """'30 to 300 MHz', '300 to 1000 MHz', '1 to 2 GHz'."""
        scale, unit = (1e9, "GHz") if self.low_hz >= 1e9 else (1e6, "MHz")
        return f"{self.low_hz / scale:g} to {self.high_hz / scale:g} {unit}"


BANDS: tuple[Band, ...] = (
    Band("HF", 3e6, 30e6),
    Band("VHF", 30e6, 300e6),
    Band("UHF", 300e6, 1e9),
    Band("L", 1e9, 2e9),
    Band("S", 2e9, 4e9),
    Band("C", 4e9, 8e9),
    Band("X", 8e9, 12e9),
    Band("Ku", 12e9, 18e9),
    Band("K", 18e9, 27e9),
    Band("Ka", 27e9, 40e9),
)


def band_for(fc_hz: float, bands: Sequence[Band] = BANDS) -> Band | None:
    """The narrowest band that contains fc, or None when no band does.

    A tie between bands of the same width goes to the band listed first.
    """
    found = [(b.width_hz, i, b) for i, b in enumerate(bands) if b.contains(fc_hz)]
    return min(found)[2] if found else None


def band_named(name: str, bands: Sequence[Band] = BANDS) -> Band | None:
    """The band of this name, compared without letter case and surrounding spaces."""
    key = name.strip().casefold()
    return next((b for b in bands if b.name.casefold() == key), None) if key else None


def bands_text(bands: Sequence[Band] = BANDS) -> str:
    """'HF 3 to 30 MHz, VHF 30 to 300 MHz, ...' for a tooltip."""
    return ", ".join(f"{b.name} {b.range_text}" for b in bands)
