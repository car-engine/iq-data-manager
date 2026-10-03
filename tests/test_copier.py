"""Tests for iqdm.transfer.copier on synthetic recordings under tmp_path."""

import hashlib
import io
import os
import sys
from pathlib import Path

import pytest

from conftest import recording_from
from iqdm.scan.scanner import scan_recording
from iqdm.transfer.copier import (
    CopyItem,
    CopyProgress,
    copy_files,
    local_path,
    partial_path,
)
from iqdm.transfer.manifest import ManifestError
from iqdm.transfer.power import ES_CONTINUOUS, ES_SYSTEM_REQUIRED, keep_awake
from iqdm.transfer.selection import select_from_scan

T0 = 1790733600.0


def items_of(info, **select_kw) -> list[CopyItem]:
    sel = select_from_scan(
        recording_from(info), scan_recording(Path(info.root), info.file_duration_s), **select_kw
    )
    return [CopyItem(rel_path=f.rel_path, size=f.size) for f in sel.files]


def tree(root: Path) -> dict[str, bytes]:
    """Every file under root by '/'-separated relative path."""
    if not root.exists():
        return {}
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def no_sleep(_s: float) -> None:
    pass


@pytest.fixture
def rec(make_recording):
    return make_recording(n_channels=2, n_slots=5, gaps=frozenset({2}))


def test_copies_every_file_byte_for_byte(rec, tmp_path):
    src = Path(rec.root)
    before = tree(src)
    dest = tmp_path / "out"
    items = items_of(rec)
    result = copy_files(src, dest, items)
    assert result.ok
    assert result.copied == tuple(i.rel_path for i in items)
    assert result.skipped == ()
    assert result.bytes_copied == sum(i.size for i in items)
    assert tree(dest) == {i.rel_path: before[i.rel_path] for i in items}
    assert tree(src) == before  # the source is unchanged


def test_modification_times_are_kept(rec, tmp_path):
    src = Path(rec.root)
    rel = "0/1790733600.dat"
    os.utime(src / rel, ns=(1_700_000_000_000_000_000, 1_700_000_123_456_789_000))
    copy_files(src, tmp_path / "out", items_of(rec))
    assert (tmp_path / "out" / rel).stat().st_mtime_ns == (src / rel).stat().st_mtime_ns


def test_only_the_selected_files_are_copied(rec, tmp_path):
    items = items_of(rec, channels=[1], start_unix=T0 + 1, end_unix=T0 + 4)
    copy_files(Path(rec.root), tmp_path / "out", items)
    assert sorted(tree(tmp_path / "out")) == ["1/1790733601.dat", "1/1790733603.dat"]


def test_source_hashes_are_computed_while_copying(rec, tmp_path):
    src = Path(rec.root)
    result = copy_files(src, tmp_path / "out", items_of(rec), hash_source=True)
    assert result.source_hashes == {
        rel: hashlib.sha256(data).hexdigest() for rel, data in tree(src).items()
    }


def test_no_hashes_unless_asked(rec, tmp_path):
    assert copy_files(Path(rec.root), tmp_path / "out", items_of(rec)).source_hashes == {}


def test_nothing_is_written_outside_the_destination(rec, tmp_path):
    before = {p for p in tmp_path.rglob("*")}
    copy_files(Path(rec.root), tmp_path / "out", items_of(rec))
    new = {p for p in tmp_path.rglob("*")} - before
    assert all(p == tmp_path / "out" or tmp_path / "out" in p.parents for p in new)


# ---------------------------------------------------------------------------
# Existing files, resume
# ---------------------------------------------------------------------------


def test_a_file_already_in_place_with_its_size_is_skipped(rec, tmp_path):
    dest = tmp_path / "out"
    rel = "0/1790733600.dat"
    target = local_path(dest, rel)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\x01" * 4000)  # same size, other bytes: verification finds it
    result = copy_files(Path(rec.root), dest, items_of(rec))
    assert result.ok
    assert result.skipped == (rel,)
    assert rel not in result.copied
    assert target.read_bytes() == b"\x01" * 4000


def test_a_file_of_another_size_is_never_replaced(rec, tmp_path):
    dest = tmp_path / "out"
    rel = "1/1790733603.dat"
    target = local_path(dest, rel)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"keep me")
    result = copy_files(Path(rec.root), dest, items_of(rec))
    assert not result.ok
    (failure,) = result.failed
    assert failure.rel_path == rel
    assert "already in the destination" in failure.message
    assert target.read_bytes() == b"keep me"
    assert len(result.copied) == len(items_of(rec)) - 1


def test_a_folder_in_place_of_a_file_is_a_failure(rec, tmp_path):
    dest = tmp_path / "out"
    local_path(dest, "0/1790733600.dat").mkdir(parents=True)
    result = copy_files(Path(rec.root), dest, items_of(rec))
    assert [f.rel_path for f in result.failed] == ["0/1790733600.dat"]


def test_a_partial_file_is_overwritten_and_renamed(rec, tmp_path):
    dest = tmp_path / "out"
    rel = "0/1790733601.dat"
    partial = partial_path(local_path(dest, rel))
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"half a file")
    result = copy_files(Path(rec.root), dest, items_of(rec))
    assert result.ok
    assert not partial.exists()
    assert local_path(dest, rel).read_bytes() == (Path(rec.root) / rel).read_bytes()


def test_a_second_run_skips_everything(rec, tmp_path):
    dest = tmp_path / "out"
    copy_files(Path(rec.root), dest, items_of(rec))
    again = copy_files(Path(rec.root), dest, items_of(rec))
    assert again.ok
    assert again.copied == ()
    assert len(again.skipped) == len(items_of(rec))


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def test_cancel_leaves_no_incomplete_file_under_a_real_name(rec, tmp_path):
    src = Path(rec.root)
    dest = tmp_path / "out"
    calls = 0

    def cancelled() -> bool:
        nonlocal calls
        calls += 1
        return calls > 10

    result = copy_files(src, dest, items_of(rec), cancelled=cancelled, chunk_bytes=1000)
    assert result.cancelled
    assert not result.ok
    copied = tree(dest)
    finished = {rel: data for rel, data in copied.items() if not rel.endswith(".partial")}
    assert finished
    assert set(finished) == set(result.copied)
    for rel, data in finished.items():
        assert data == (src / rel).read_bytes()
    assert any(rel.endswith(".partial") for rel in copied)


def test_cancel_before_the_start_copies_nothing(rec, tmp_path):
    result = copy_files(Path(rec.root), tmp_path / "out", items_of(rec), cancelled=lambda: True)
    assert result.cancelled
    assert result.copied == ()
    assert tree(tmp_path / "out") == {}


# ---------------------------------------------------------------------------
# Failures and retries
# ---------------------------------------------------------------------------


class FlakyOpener:
    """Fails the first `failures` opens of each file, then opens it."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls: dict[Path, int] = {}

    def __call__(self, path: Path):
        self.calls[path] = self.calls.get(path, 0) + 1
        if self.calls[path] <= self.failures:
            raise OSError("the network name is no longer available")
        return path.open("rb")


def test_a_failed_read_is_retried(make_recording, tmp_path):
    info = make_recording(n_slots=2)
    pauses: list[float] = []
    result = copy_files(
        Path(info.root),
        tmp_path / "out",
        items_of(info),
        open_source=FlakyOpener(2),
        retry_pause_s=0.5,
        sleep=pauses.append,
    )
    assert result.ok
    assert len(result.copied) == 2
    assert sum(pauses) == pytest.approx(2 * 2 * 0.5)  # 2 files, 2 pauses each


def test_a_file_that_keeps_failing_is_reported(make_recording, tmp_path):
    info = make_recording(n_slots=2)
    seen: list[CopyProgress] = []
    opener = FlakyOpener(99)
    result = copy_files(
        Path(info.root),
        tmp_path / "out",
        items_of(info),
        open_source=opener,
        sleep=no_sleep,
        progress=seen.append,
    )
    assert [f.message for f in result.failed] == [
        "Copy failed after 4 attempts: the network name is no longer available"
    ] * 2
    assert set(opener.calls.values()) == {4}
    assert seen[-1].files_done == 2
    assert seen[-1].bytes_done == 0


def test_a_cancel_ends_the_retry_pause(make_recording, tmp_path):
    info = make_recording(n_slots=1)
    state = {"cancel": False}

    def sleep(_s: float) -> None:
        state["cancel"] = True

    result = copy_files(
        Path(info.root),
        tmp_path / "out",
        items_of(info),
        open_source=FlakyOpener(99),
        sleep=sleep,
        cancelled=lambda: state["cancel"],
    )
    assert result.cancelled
    assert result.failed == ()


def test_a_source_that_changed_size_since_the_scan_is_not_copied(rec, tmp_path):
    items = items_of(rec)
    (Path(rec.root) / items[0].rel_path).write_bytes(b"shorter")
    opener = FlakyOpener(0)
    result = copy_files(Path(rec.root), tmp_path / "out", items, open_source=opener)
    (failure,) = result.failed
    assert failure.rel_path == items[0].rel_path
    assert "Scan the recording again" in failure.message
    assert Path(rec.root) / items[0].rel_path not in opener.calls  # not retried


def test_a_source_that_changes_during_the_copy_fails(rec, tmp_path):
    def short_read(_path: Path):
        return io.BytesIO(b"\x00" * 100)

    result = copy_files(Path(rec.root), tmp_path / "out", items_of(rec)[:1], open_source=short_read)
    (failure,) = result.failed
    assert failure.message == "The source file changed during the copy. Scan the recording again."
    assert not local_path(tmp_path / "out", failure.rel_path).exists()


def test_a_file_that_appears_during_the_copy_is_not_replaced(rec, tmp_path):
    dest = tmp_path / "out"
    item = items_of(rec)[0]
    target = local_path(dest, item.rel_path)

    def opener(path: Path):
        target.write_bytes(b"someone else's file")
        return path.open("rb")

    result = copy_files(Path(rec.root), dest, [item], open_source=opener)
    assert [f.message for f in result.failed] == [
        "A file with this name appeared in the destination during the copy."
    ]
    assert target.read_bytes() == b"someone else's file"


# ---------------------------------------------------------------------------
# Progress, workers, arguments
# ---------------------------------------------------------------------------


def test_progress_counts_files_and_bytes(rec, tmp_path):
    seen: list[CopyProgress] = []
    items = items_of(rec)
    copy_files(Path(rec.root), tmp_path / "out", items, progress=seen.append, chunk_bytes=1500)
    total = sum(i.size for i in items)
    assert seen[-1] == CopyProgress(
        files_done=len(items), files_total=len(items), bytes_done=total, bytes_total=total
    )
    assert [p.bytes_done for p in seen] == sorted(p.bytes_done for p in seen)
    assert len(seen) > len(items)  # several chunks per file


@pytest.mark.parametrize("workers", [2, 4, 8])
def test_several_workers_give_the_same_copy(make_recording, tmp_path, workers):
    info = make_recording(n_channels=3, n_slots=20)
    dest = tmp_path / f"out{workers}"
    result = copy_files(Path(info.root), dest, items_of(info), workers=workers, hash_source=True)
    assert result.ok
    assert result.copied == tuple(i.rel_path for i in items_of(info))
    assert tree(dest) == tree(Path(info.root))
    assert len(result.source_hashes) == 60


@pytest.mark.parametrize(("fsync", "expected"), [(True, 8), (False, 0)])
def test_each_file_is_flushed_unless_turned_off(rec, tmp_path, monkeypatch, fsync, expected):
    from iqdm.transfer import copier

    calls: list[int] = []
    monkeypatch.setattr(copier.os, "fsync", calls.append)
    result = copy_files(Path(rec.root), tmp_path / "out", items_of(rec), fsync=fsync)
    assert result.ok
    assert len(calls) == expected
    assert tree(tmp_path / "out") == tree(Path(rec.root))


def test_workers_must_be_positive(rec, tmp_path):
    with pytest.raises(ValueError, match="workers"):
        copy_files(Path(rec.root), tmp_path / "out", items_of(rec), workers=0)


@pytest.mark.parametrize("rel", ["../escape.dat", "0/../../x.dat", "C:/x.dat"])
def test_unsafe_paths_are_refused_before_anything_is_written(rec, tmp_path, rel):
    items = [*items_of(rec), CopyItem(rel_path=rel, size=1)]
    with pytest.raises(ManifestError):
        copy_files(Path(rec.root), tmp_path / "out", items)
    assert not (tmp_path / "out").exists()


# ---------------------------------------------------------------------------
# Keeping Windows awake
# ---------------------------------------------------------------------------


def test_keep_awake_sets_and_resets_the_state():
    calls: list[int] = []
    with keep_awake(calls.append):
        assert calls == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED]
    assert calls == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED, ES_CONTINUOUS]


def test_keep_awake_resets_after_an_error():
    calls: list[int] = []
    with pytest.raises(RuntimeError), keep_awake(calls.append):
        raise RuntimeError("copy failed")
    assert calls[-1] == ES_CONTINUOUS


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_keep_awake_calls_windows():
    with keep_awake():
        pass
