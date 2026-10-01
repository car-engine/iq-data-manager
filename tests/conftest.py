"""Shared pytest setup."""

import itertools
import os
from collections.abc import Callable

import pytest

# Run Qt without a display so GUI tests open no windows. Set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# tools/ is on the pytest pythonpath (see pyproject.toml).
import make_fixtures
from make_fixtures import FixtureInfo, RecordingSpec


@pytest.fixture
def make_recording(tmp_path) -> Callable[..., FixtureInfo]:
    """Factory that creates a synthetic recording in a new folder under tmp_path.

    Call with a RecordingSpec, or with RecordingSpec keyword arguments:
        info = make_recording(n_channels=2, gaps=frozenset({3}))
    """
    counter = itertools.count()

    def _make(spec: RecordingSpec | None = None, **kwargs) -> FixtureInfo:
        out = tmp_path / f"rec{next(counter)}"
        return make_fixtures.make_recording(out, spec or RecordingSpec(**kwargs))

    return _make
