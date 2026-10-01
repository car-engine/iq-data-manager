"""UTC time helpers. The app never uses local time.

Stored timestamps are ISO 8601 UTC text in whole seconds, e.g. '2026-09-30T08:15:00Z',
and Unix seconds as floats.
"""

import math
import re
from datetime import UTC, datetime

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def utc_now_iso(now: datetime | None = None) -> str:
    """Current UTC time as ISO 8601 text. `now` must be timezone-aware if given."""
    moment = datetime.now(UTC) if now is None else now
    if moment.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return moment.astimezone(UTC).strftime(ISO_FORMAT)


def unix_to_iso(t: float) -> str:
    """Unix seconds as ISO 8601 UTC text. Fractional seconds are truncated toward -inf."""
    return datetime.fromtimestamp(math.floor(t), tz=UTC).strftime(ISO_FORMAT)


def iso_to_unix(text: str) -> float:
    """Parse ISO 8601 UTC text in the stored form 'YYYY-MM-DDTHH:MM:SSZ'."""
    if not _ISO_RE.match(text):
        raise ValueError(f"expected 'YYYY-MM-DDTHH:MM:SSZ', got {text!r}")
    return datetime.fromisoformat(text).timestamp()
