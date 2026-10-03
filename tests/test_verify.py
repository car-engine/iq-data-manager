"""Tests for iqdm.transfer.verify on synthetic recordings under tmp_path."""

import hashlib
from pathlib import Path

import pytest

from conftest import recording_from
from iqdm.models import HashMode
from iqdm.scan.scanner import scan_recording
from iqdm.transfer.copier import CopyItem, copy_files, local_path
from iqdm.transfer.selection import select_from_scan
from iqdm.transfer.verify import (
    ProblemKind,
    VerifyProgress,
    file_sha256,
    hash_targets,
    hashed_paths,
    sample_paths,
    verify_copy,
)


def items_of(info) -> list[CopyItem]:
    sel = select_from_scan(recording_from(info), scan_recording(Path(info.root), 1.0))
    return [CopyItem(rel_path=f.rel_path, size=f.size) for f in sel.files]


@pytest.fixture
def copied(make_recording, tmp_path):
    """A 2-channel recording of 10 files each, copied to tmp_path/out."""
    info = make_recording(n_channels=2, n_slots=10)
    items = items_of(info)
    dest = tmp_path / "out"
    assert copy_files(Path(info.root), dest, items).ok
    return Path(info.root), dest, items


def verify(copied, mode=HashMode.ALL, fraction=0.05, **kw):
    source, dest, items = copied
    return verify_copy(source, dest, items, hash_mode=mode, sample_fraction=fraction, **kw)


def test_a_good_copy_passes_with_every_hash(copied):
    result = verify(copied)
    assert result.passed
    assert result.problems == ()
    assert len(result.hashes) == 20
    _, dest, items = copied
    rel = items[0].rel_path
    assert result.hashes[rel] == hashlib.sha256(local_path(dest, rel).read_bytes()).hexdigest()


def test_sample_mode_hashes_a_fraction_of_the_files(copied):
    assert len(verify(copied, HashMode.SAMPLE, 0.05).hashes) == 1
    assert len(verify(copied, HashMode.SAMPLE, 0.25).hashes) == 5


def test_no_hash_mode_compares_sizes_only(copied):
    _, dest, items = copied
    local_path(dest, items[3].rel_path).write_bytes(b"\xff" * items[3].size)
    result = verify(copied, HashMode.NONE)
    assert result.passed
    assert result.hashes == {}


def test_a_missing_file_fails(copied):
    _, dest, items = copied
    local_path(dest, items[0].rel_path).rename(dest / "moved-away.txt")
    result = verify(copied, HashMode.NONE)
    assert not result.passed
    assert [(p.rel_path, p.kind) for p in result.problems] == [
        (items[0].rel_path, ProblemKind.MISSING)
    ]


def test_a_size_difference_fails(copied):
    _, dest, items = copied
    local_path(dest, items[5].rel_path).write_bytes(b"short")
    (problem,) = verify(copied, HashMode.NONE).problems
    assert problem.kind is ProblemKind.SIZE
    assert problem.message == "5 bytes in the destination, 4,000 in the source."


def test_a_content_difference_fails_when_the_file_is_hashed(copied):
    _, dest, items = copied
    local_path(dest, items[7].rel_path).write_bytes(b"\xff" * items[7].size)
    (problem,) = verify(copied, HashMode.ALL).problems
    assert (problem.rel_path, problem.kind) == (items[7].rel_path, ProblemKind.HASH)


def test_source_hashes_from_the_copy_are_used(copied):
    _, _, items = copied
    rel = items[2].rel_path
    (problem,) = verify(copied, source_hashes={rel: "0" * 64}).problems
    assert (problem.rel_path, problem.kind) == (rel, ProblemKind.HASH)


def test_an_unreadable_source_is_a_problem(copied, tmp_path):
    _, dest, items = copied
    empty = tmp_path / "empty"
    empty.mkdir()
    result = verify_copy(empty, dest, items[:1], hash_mode=HashMode.ALL, sample_fraction=1)
    (problem,) = result.problems
    assert problem.kind is ProblemKind.UNREADABLE
    assert problem.message.startswith("Cannot read the file:")


def test_extra_files_are_reported_and_do_not_fail(copied):
    _, dest, _ = copied
    (dest / "0" / "notes.txt").write_text("x", encoding="utf-8")
    (dest / "1" / "1790733700.dat.partial").write_bytes(b"x")
    (dest / "elsewhere").mkdir()
    (dest / "elsewhere" / "x.dat").write_bytes(b"x")
    result = verify(copied, HashMode.NONE)
    assert result.passed
    assert result.extra == ("0/notes.txt", "1/1790733700.dat.partial")


def test_cancel_stops_the_check(copied):
    calls = 0

    def cancelled() -> bool:
        nonlocal calls
        calls += 1
        return calls > 5

    result = verify(copied, cancelled=cancelled)
    assert result.cancelled
    assert not result.passed


def test_progress_counts_the_files(copied):
    seen: list[VerifyProgress] = []
    verify(copied, HashMode.NONE, progress=seen.append)
    assert seen[-1] == VerifyProgress(files_done=20, files_total=20)
    assert len(seen) == 20


def test_progress_counts_the_hashed_bytes(copied):
    seen: list[VerifyProgress] = []
    verify(copied, HashMode.SAMPLE, 0.25, progress=seen.append)
    assert seen[-1] == VerifyProgress(
        files_done=20, files_total=20, bytes_done=5 * 4000, bytes_total=5 * 4000
    )
    assert [p.bytes_done for p in seen] == sorted(p.bytes_done for p in seen)


# ---------------------------------------------------------------------------
# Skipped files (D63) and reading past the cache (D55)
# ---------------------------------------------------------------------------


def outside_the_sample(items, fraction=0.05) -> CopyItem:
    chosen = sample_paths([i.rel_path for i in items], fraction)
    return next(i for i in items if i.rel_path not in chosen)


def test_a_skipped_file_with_other_content_fails_in_sample_mode(copied):
    _, dest, items = copied
    stranger = outside_the_sample(items)
    local_path(dest, stranger.rel_path).write_bytes(b"\xff" * stranger.size)
    assert verify(copied, HashMode.SAMPLE).passed  # trusted by size before D63
    result = verify(copied, HashMode.SAMPLE, skipped=[stranger.rel_path])
    (problem,) = result.problems
    assert (problem.rel_path, problem.kind) == (stranger.rel_path, ProblemKind.HASH)


def test_skipped_files_are_not_hashed_in_mode_none(copied):
    _, dest, items = copied
    stranger = items[0]
    local_path(dest, stranger.rel_path).write_bytes(b"\xff" * stranger.size)
    result = verify(copied, HashMode.NONE, skipped=[stranger.rel_path])
    assert result.passed
    assert result.hashes == {}


def test_hashed_paths_add_the_skipped_files():
    paths = [f"0/{1790733600 + i}.dat" for i in range(40)]
    sample = hash_targets(paths, HashMode.SAMPLE, 0.05)
    extra = {p for p in paths if p not in sample}
    skipped = sorted(extra)[:3]
    assert hashed_paths(paths, HashMode.SAMPLE, 0.05, skipped) == sample | set(skipped)
    assert hashed_paths(paths, HashMode.NONE, 0.05, skipped) == frozenset()
    assert hashed_paths(paths, HashMode.SAMPLE, 0.05, ["not/listed.dat"]) == sample


def test_uncached_verification_gives_the_same_result(copied):
    _, dest, items = copied
    local_path(dest, items[4].rel_path).write_bytes(b"\xff" * items[4].size)
    cached = verify(copied, HashMode.ALL)
    uncached = verify(copied, HashMode.ALL, uncached=True)
    assert uncached.problems == cached.problems
    assert uncached.hashes == cached.hashes


# ---------------------------------------------------------------------------
# Sample choice
# ---------------------------------------------------------------------------


def test_the_sample_depends_only_on_the_paths():
    paths = [f"0/{1790733600 + i}.dat" for i in range(100)]
    first = sample_paths(paths, 0.05)
    assert len(first) == 5
    assert sample_paths(reversed(paths), 0.05) == first
    assert first <= sample_paths(paths, 0.5)


@pytest.mark.parametrize(
    ("n", "fraction", "size"), [(1, 0.05, 1), (19, 0.05, 1), (21, 0.05, 2), (4, 1, 4)]
)
def test_sample_size_rounds_up_and_is_at_least_one(n, fraction, size):
    assert len(sample_paths([f"{i}.dat" for i in range(n)], fraction)) == size


def test_sample_of_nothing_is_empty():
    assert sample_paths([], 0.05) == frozenset()


@pytest.mark.parametrize("fraction", [0, -0.1, 1.5])
def test_sample_fraction_must_be_in_range(fraction):
    with pytest.raises(ValueError, match="fraction"):
        sample_paths(["a.dat"], fraction)


def test_hash_targets_by_mode():
    paths = ["a.dat", "b.dat", "c.dat"]
    assert hash_targets(paths, HashMode.NONE, 0.5) == frozenset()
    assert hash_targets(paths, HashMode.ALL, 0.5) == frozenset(paths)
    assert len(hash_targets(paths, HashMode.SAMPLE, 0.5)) == 2


def test_file_sha256_reads_in_chunks(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(bytes(range(256)) * 10)
    assert file_sha256(path, chunk_bytes=7) == hashlib.sha256(path.read_bytes()).hexdigest()
