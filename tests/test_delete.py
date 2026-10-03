"""Tests for iqdm.transfer.delete. Every file it deletes lives under tmp_path.

Each test builds a laptop folder with make_fixtures, copies it to a "NAS" folder under
tmp_path with the copy engine, and deletes from the laptop folder.
"""

import dataclasses
from pathlib import Path

import pytest

from conftest import recording_from
from iqdm.models import ArchiveState, HashMode, Operation, TransferEntry, Verification
from iqdm.scan.scanner import scan_recording
from iqdm.transfer.copier import CopyItem, copy_files, local_path
from iqdm.transfer.delete import (
    NOT_CHECKED,
    DeleteRefused,
    checked_before_delete,
    delete_source_files,
    prepare_delete,
)
from iqdm.transfer.manifest import Manifest, ManifestFile
from iqdm.transfer.selection import select_from_scan


def check_of(archive: TransferEntry, **kw) -> TransferEntry:
    """A passed check before delete of `archive`, started after it finished (D55)."""
    values = {
        "id": 9,
        "recording_id": archive.recording_id,
        "operation": Operation.CHECK,
        "parent_id": archive.id,
        "source": archive.source,
        "destination": archive.destination,
        "started_at": "2026-10-03T09:00:00Z",
        "finished_at": "2026-10-03T09:10:00Z",
        "performed_by": "tester",
        "verification": Verification.PASS,
    } | kw
    return TransferEntry(**values)


@dataclasses.dataclass
class Scenario:
    source: Path
    dest: Path
    manifest: Manifest
    archive: TransferEntry
    rec: object
    history: list[TransferEntry] | None = None

    def plan(self):
        history = [check_of(self.archive)] if self.history is None else self.history
        return prepare_delete(self.archive, self.manifest, self.rec, history)


@pytest.fixture
def archived(make_recording, tmp_path):
    def build(**spec) -> Scenario:
        info = make_recording(**({"n_channels": 2, "n_slots": 4} | spec))
        src = Path(info.root)
        sel = select_from_scan(recording_from(info), scan_recording(src, 1.0))
        items = [CopyItem(rel_path=f.rel_path, size=f.size) for f in sel.files]
        dest = tmp_path / "nas" / "2026" / src.name
        assert copy_files(src, dest, items).ok
        manifest = Manifest(
            transfer_id=5,
            recording_id=1,
            operation=Operation.ARCHIVE,
            source=str(src),
            destination=str(dest),
            range_start_unix=None,
            range_end_unix=None,
            channels=None,
            hash_mode=HashMode.SAMPLE,
            created_at="2026-10-03T08:00:00Z",
            files=tuple(ManifestFile(path=i.rel_path, size=i.size) for i in items),
        )
        archive = TransferEntry(
            id=5,
            recording_id=1,
            operation=Operation.ARCHIVE,
            source=str(src),
            destination=str(dest),
            started_at="2026-10-03T07:00:00Z",
            finished_at="2026-10-03T08:00:00Z",
            performed_by="tester",
            verification=Verification.PASS,
            manifest_path="C:/app/manifests/transfer-5.json",
            manifest_sha256="ab" * 32,
        )
        rec = recording_from(
            info,
            id=1,
            storage_root=str(dest.parent),
            rel_path=dest.name,
            archive_state=ArchiveState.ARCHIVED,
            archived_at="2026-10-03T08:00:00Z",
        )
        return Scenario(src, dest, manifest, archive, rec)

    return build


def files_under(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) if root.exists() else []


def test_deletes_every_listed_file_and_the_empty_folders(archived):
    s = archived()
    nas_before = files_under(s.dest)
    result = delete_source_files(s.plan())
    assert result.complete
    assert result.deleted == tuple(f.path for f in s.manifest.files)
    assert result.kept == ()
    assert result.folders_removed == ("0", "1", "")
    assert not s.source.exists()
    assert files_under(s.dest) == nas_before  # the NAS copy is untouched


def test_files_not_in_the_manifest_stay(archived):
    s = archived(junk=True)
    unlisted = set(files_under(s.source)) - {f.path for f in s.manifest.files} - {"0", "1"}
    assert unlisted  # make_fixtures wrote files a scanner ignores
    result = delete_source_files(s.plan())
    assert result.complete
    assert set(files_under(s.source)) >= unlisted
    assert "" not in result.folders_removed


def test_a_range_manifest_deletes_only_its_files(archived):
    s = archived()
    s.manifest = dataclasses.replace(s.manifest, files=s.manifest.files[:2])
    delete_source_files(s.plan())
    remaining = [p for p in files_under(s.source) if p.endswith(".dat")]
    assert len(remaining) == 6
    assert all(f.path not in remaining for f in s.manifest.files)


def test_a_changed_nas_copy_keeps_the_laptop_file(archived):
    s = archived()
    rel = s.manifest.files[1].path
    local_path(s.dest, rel).write_bytes(b"truncated")
    result = delete_source_files(s.plan())
    assert not result.complete
    assert [(k.rel_path, k.reason) for k in result.kept] == [
        (rel, "The NAS copy is missing or has another size.")
    ]
    assert local_path(s.source, rel).exists()
    assert len(result.deleted) == 7
    assert "0" not in result.folders_removed


def test_a_missing_nas_copy_keeps_the_laptop_file(archived):
    s = archived()
    rel = s.manifest.files[0].path
    local_path(s.dest, rel).rename(s.dest / "elsewhere.dat")
    result = delete_source_files(s.plan())
    assert [k.rel_path for k in result.kept] == [rel]
    assert local_path(s.source, rel).exists()


def test_a_laptop_file_changed_after_the_copy_is_kept(archived):
    s = archived()
    rel = s.manifest.files[3].path
    local_path(s.source, rel).write_bytes(b"new data")
    result = delete_source_files(s.plan())
    assert [(k.rel_path, k.reason) for k in result.kept] == [
        (rel, "The laptop file changed after the copy.")
    ]
    assert local_path(s.source, rel).read_bytes() == b"new data"


def test_a_file_already_gone_is_reported_and_a_rerun_finishes(archived):
    s = archived()
    rel = s.manifest.files[0].path
    local_path(s.dest, rel).write_bytes(b"x")  # first run keeps this one
    first = delete_source_files(s.plan())
    assert [k.rel_path for k in first.kept] == [rel]
    local_path(s.dest, rel).write_bytes(local_path(s.source, rel).read_bytes())
    second = delete_source_files(s.plan())
    assert second.complete
    assert second.deleted == (rel,)
    assert len(second.already_gone) == 7
    assert not s.source.exists()


def test_a_link_in_place_of_a_laptop_file_is_kept(archived, tmp_path):
    s = archived()
    rel = s.manifest.files[0].path
    src = local_path(s.source, rel)
    outside = tmp_path / "outside.dat"
    outside.write_bytes(src.read_bytes())
    src.rename(tmp_path / "set-aside.dat")
    try:
        src.symlink_to(outside)
    except OSError:
        pytest.skip("creating symbolic links needs a privilege this account lacks")
    result = delete_source_files(s.plan())
    assert [k.rel_path for k in result.kept] == [rel]
    assert outside.exists()


def test_cancel_stops_before_the_next_file(archived):
    s = archived()
    calls = 0

    def cancelled() -> bool:
        nonlocal calls
        calls += 1
        return calls > 3

    result = delete_source_files(s.plan(), cancelled=cancelled)
    assert result.cancelled
    assert not result.complete
    assert len(result.deleted) == 3
    assert result.folders_removed == ()


def test_progress_counts_the_files(archived):
    s = archived()
    seen: list[int] = []
    delete_source_files(s.plan(), progress=seen.append)
    assert seen == list(range(1, 9))


# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"verification": Verification.FAIL}, "did not pass its check"),
        ({"verification": Verification.SKIPPED}, "did not pass its check"),
        ({"finished_at": None}, "did not pass its check"),
        ({"operation": Operation.COPY}, "Only the laptop copy"),
        ({"manifest_path": None}, "has no file list"),
        ({"manifest_sha256": None}, "has no file list"),
        ({"id": 6}, "belongs to another transfer"),
        ({"id": None}, "no entry in the transfer history"),
        ({"recording_id": 2}, "belongs to another recording"),
    ],
)
def test_the_archive_must_be_a_passed_archive_with_its_manifest(archived, change, reason):
    s = archived()
    s.archive = dataclasses.replace(s.archive, **change)
    with pytest.raises(DeleteRefused, match=reason):
        s.plan()
    assert len(files_under(s.source)) == 10  # 8 files and 2 channel folders


@pytest.mark.parametrize(
    "change",
    [
        {"transfer_id": 9},
        {"recording_id": 2},
        {"operation": Operation.COPY},
        {"source": "C:/other"},
        {"destination": "C:/other"},
    ],
)
def test_the_manifest_must_belong_to_the_archive(archived, change):
    s = archived()
    s.manifest = dataclasses.replace(s.manifest, **change)
    with pytest.raises(DeleteRefused, match="belongs to another transfer"):
        s.plan()


def test_paths_compare_without_letter_case(archived):
    s = archived()
    s.manifest = dataclasses.replace(s.manifest, source=s.manifest.source.upper())
    assert s.plan().files == s.manifest.files


@pytest.mark.parametrize(
    "change",
    [
        {"archive_state": ArchiveState.LOCAL, "archived_at": None},
        {"rel_path": "another-folder"},
    ],
)
def test_the_recording_must_point_at_the_archive_copy(archived, change):
    s = archived()
    s.rec = dataclasses.replace(s.rec, **change)
    with pytest.raises(DeleteRefused, match="no longer points at the archive copy"):
        s.plan()


def test_source_and_destination_must_differ(archived):
    s = archived()
    same = str(s.source)
    s.archive = dataclasses.replace(s.archive, destination=same)
    s.manifest = dataclasses.replace(s.manifest, destination=same)
    s.rec = dataclasses.replace(s.rec, storage_root=str(s.source.parent), rel_path=s.source.name)
    with pytest.raises(DeleteRefused, match="same folder"):
        s.plan()


def test_an_unsafe_manifest_path_is_refused(archived):
    s = archived()
    bad = ManifestFile(path="../escape.dat", size=1)
    s.manifest = dataclasses.replace(s.manifest, files=(*s.manifest.files, bad))
    with pytest.raises(DeleteRefused, match="not a relative path"):
        s.plan()


# ---------------------------------------------------------------------------
# Check before delete (D55)
# ---------------------------------------------------------------------------


def test_no_check_before_delete_is_refused(archived):
    s = archived()
    s.history = []
    with pytest.raises(DeleteRefused, match="Check before delete") as refused:
        s.plan()
    assert refused.value.reasons == (NOT_CHECKED,)
    assert len(files_under(s.source)) == 10


@pytest.mark.parametrize(
    "change",
    [
        {"verification": Verification.FAIL},
        {"verification": Verification.SKIPPED},
        {"finished_at": None},
        {"parent_id": 6},  # another archive
        {"parent_id": None},  # a Check archive, which reads no file contents
        {"operation": Operation.COPY, "parent_id": None},
        {"started_at": "2026-10-03T07:59:59Z"},  # before the archive finished
    ],
)
def test_only_a_passed_later_check_of_this_archive_counts(archived, change):
    s = archived()
    s.history = [check_of(s.archive, **change)]
    with pytest.raises(DeleteRefused, match="Check before delete"):
        s.plan()
    assert not checked_before_delete(s.archive, s.history)


def test_a_check_at_the_finish_time_counts(archived):
    s = archived()
    s.history = [check_of(s.archive, started_at=s.archive.finished_at)]
    assert s.plan().files == s.manifest.files


def test_one_passed_check_among_failed_ones_counts(archived):
    s = archived()
    s.history = [
        check_of(s.archive, verification=Verification.FAIL),
        check_of(s.archive, id=10),
    ]
    assert checked_before_delete(s.archive, s.history)
