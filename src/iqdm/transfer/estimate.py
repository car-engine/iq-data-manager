"""Time estimates for the transfer preview (SPEC section 8).

The copy time is the bytes still to copy at network_speed_mb_s. Hashing during
verification reads the hashed destination files back over the network at the same
speed. Source files the copy did not read, because they were already in place, are
also read for their hashes. MB here means 10**6 bytes.
"""

import math
from dataclasses import dataclass

MB = 1_000_000


@dataclass(frozen=True, kw_only=True)
class Estimate:
    copy_s: float
    hash_s: float

    @property
    def total_s(self) -> float:
        return self.copy_s + self.hash_s


def estimate(
    *, bytes_to_copy: int, hashed_bytes: int, speed_mb_s: float, rehashed_source_bytes: int = 0
) -> Estimate:
    """Copy and hash times. rehashed_source_bytes are skipped files the hash re-reads."""
    if speed_mb_s <= 0:
        raise ValueError(f"speed_mb_s must be positive, got {speed_mb_s}")
    rate = speed_mb_s * MB
    return Estimate(
        copy_s=bytes_to_copy / rate,
        hash_s=(hashed_bytes + rehashed_source_bytes) / rate,
    )


def duration_text(seconds: float) -> str:
    """'under a minute', 'about 1 min', 'about 45 min', 'about 2 h 30 min'."""
    if seconds < 60:
        return "under a minute"
    minutes = math.ceil(seconds / 60)
    if minutes < 60:
        return f"about {minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"about {hours} h" if rest == 0 else f"about {hours} h {rest} min"
