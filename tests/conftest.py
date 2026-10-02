"""Shared pytest setup."""

import itertools
import os
from collections.abc import Callable
from pathlib import Path

import pytest

# Run Qt without a display so GUI tests open no windows. Set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# make_fixtures lives in tools/, which is on the pytest pythonpath (see pyproject.toml).
import make_fixtures
from iqdm.db.connection import create_database
from iqdm.models import Channel, Recording
from make_fixtures import FixtureInfo, RecordingSpec


@pytest.fixture
def db_path(tmp_path) -> Path:
    """A fresh database created from schema.sql under tmp_path."""
    path = tmp_path / "catalog.db"
    create_database(path)
    return path


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


def recording_from(info: FixtureInfo, *, site_id: int = 1, **kw) -> Recording:
    """A catalogue entry that matches a generated recording, located where it lies."""
    root = Path(info.root)
    values = {
        "logged_by": "tester",
        "site_id": site_id,
        "storage_root": str(root.parent),
        "rel_path": root.name,
        "file_duration_s": info.file_duration_s,
        "channels": [
            Channel(
                channel_index=c.index,
                sub_path=c.sub_path,
                fc_hz=100e6 + c.index * 1e6,
                fs_hz=info.fs_hz,
                start_unix=c.start_unix,
                end_unix=c.end_unix,
                n_files=c.n_files,
                total_bytes=c.total_bytes,
            )
            for c in info.channels
            if c.start_unix is not None
        ],
    } | kw
    return Recording(**values)


@pytest.fixture
def entry_for() -> Callable[..., Recording]:
    """recording_from() as a fixture: entry_for(info, **Recording overrides)."""
    return recording_from
