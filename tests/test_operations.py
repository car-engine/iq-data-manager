"""End-to-end tests for iqdm.transfer.operations.

Each test uses a fresh database, a "laptop" recording made by make_fixtures and a
"NAS" folder, all under tmp_path. The NAS root is a tmp_path folder given to Config
directly; no network path is used.
"""

import itertools
from pathlib import Path

import pytest

from conftest import recording_from
from iqdm import viewer
from iqdm.config import Config
from iqdm.db import repository as repo
from iqdm.db.connection import open_db, write_transaction
from iqdm.models import ArchiveState, HashMode, Operation, Verification
from iqdm.transfer.copier import CopyProgress, local_path
from iqdm.transfer.delete import DeleteRefused
from iqdm.transfer.manifest import read_manifest
from iqdm.transfer.operations import (
    TransferError,
    TransferRequest,
    check_archive,
    delete_laptop_copy,
    preview_transfer,
    run_transfer,
)
from iqdm.transfer.pathcheck import DiskUsage
from iqdm.transfer.verify import hash_targets

T0 = 1790733600.0


def plenty(_path) -> DiskUsage:
    return DiskUsage(10**15, 0, 10**15)


class Env:
    def __init__(self, tmp_path: Path, db_path: Path, info) -> None:
        self.tmp = tmp_path
        self.db = db_path
        self.info = info
        self.source = Path(info.root)
        self.nas = tmp_path / "nas"
        self.nas.mkdir()
        self.manifests = tmp_path / "app" / "manifests"
        self.config = Config(nas_roots=(str(self.nas),), hash_sample_fraction=0.25)
        ticks = itertools.count()
        self.now = lambda: f"2026-10-03T08:{next(ticks) % 60:02d}:00Z"

        def insert(conn):
            site = repo.add_site(conn, "SiteA").id
            return repo.insert_recording(conn, recording_from(info, site_id=site))

        self.rid = write_transaction(db_path, insert)

    def request(self, operation=Operation.ARCHIVE, dest=None, hash_mode=HashMode.ALL, **kw):
        if dest is None:
            dest = self.nas / "2026" / self.source.name
        return TransferRequest(
            recording_id=self.rid,
            operation=operation,
            destination=str(dest),
            hash_mode=hash_mode,
            **kw,
        )

    def preview(self, request, resolve_drive=None):
        return preview_transfer(
            self.db,
            request,
            self.config,
            resolve_drive=resolve_drive,
            disk_usage=plenty,
            long_paths=True,
        )

    def run(self, preview, **kw):
        values = {
            "performed_by": "userA",
            "manifests_dir": self.manifests,
            "now": self.now,
        } | kw
        return run_transfer(self.db, preview, **values)

    def recording(self):
        with open_db(self.db, readonly=True) as conn:
            return repo.get_recording(conn, self.rid)

    def transfers(self):
        with open_db(self.db, readonly=True) as conn:
            return repo.list_transfers(conn, self.rid)


@pytest.fixture
def env(tmp_path, db_path, make_recording) -> Env:
    return Env(tmp_path, db_path, make_recording(n_channels=2, n_slots=6, gaps=frozenset({3})))


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# ---------------------------------------------------------------------------
# Copy
# ---------------------------------------------------------------------------


def test_copy_of_the_whole_recording(env):
    dest = env.tmp / "pc" / "rec"
    preview = env.preview(env.request(Operation.COPY, dest))
    assert preview.ok, preview.errors
    assert preview.selection.n_files == 10
    assert preview.hashed_files == 10
    out = env.run(preview)
    assert out.passed
    assert tree(dest) == tree(env.source)
    (row,) = env.transfers()
    assert row.operation is Operation.COPY
    assert row.verification is Verification.PASS
    assert (row.n_files, row.total_bytes) == (10, 40_000)
    assert row.hash_mode is HashMode.ALL
    stamp = row.finished_at.replace("-", "").replace(":", "")
    assert row.manifest_path == str(env.manifests / f"transfer-{row.id}-{stamp}.json")
    manifest = read_manifest(Path(row.manifest_path), row.manifest_sha256)
    assert len(manifest.files) == 10
    assert all(f.sha256 for f in manifest.files)
    assert env.recording().archive_state is ArchiveState.LOCAL


def test_copy_of_a_range_and_a_channel(env):
    dest = env.tmp / "pc" / "part"
    request = env.request(
        Operation.COPY, dest, HashMode.SAMPLE, channels=(1,), start_unix=T0 + 1, end_unix=T0 + 5
    )
    out = env.run(env.preview(request))
    assert out.passed
    assert sorted(tree(dest)) == [f"1/{int(T0) + i}.dat" for i in (1, 2, 4)]
    (row,) = env.transfers()
    assert (row.range_start_unix, row.range_end_unix, row.channels) == (T0 + 1, T0 + 5, (1,))
    manifest = read_manifest(Path(row.manifest_path))
    assert sum(1 for f in manifest.files if f.sha256) == 1  # ceil(0.25 * 3)


def test_a_copy_failure_is_recorded(env):
    dest = env.tmp / "pc" / "rec"
    preview = env.preview(env.request(Operation.COPY, dest))
    target = local_path(dest, preview.selection.files[0].rel_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"appeared after the preview")
    out = env.run(preview)
    assert out.verification is Verification.FAIL
    assert out.notes.startswith("Could not copy 1 file: 0/1790733600.dat")
    (row,) = env.transfers()
    assert row.verification is Verification.FAIL
    assert row.manifest_path is None


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


def test_archive_points_the_recording_at_the_nas(env):
    dest = env.nas / "2026" / env.source.name
    out = env.run(env.preview(env.request()))
    assert out.passed
    rec = env.recording()
    assert rec.archive_state is ArchiveState.ARCHIVED
    assert (rec.storage_root, rec.rel_path) == (str(env.nas), f"2026\\{env.source.name}")
    (row,) = env.transfers()
    assert rec.archived_at == row.finished_at
    assert row.operation is Operation.ARCHIVE
    assert tree(dest) == tree(env.source)  # the laptop copy stays until it is deleted


@pytest.mark.parametrize(
    ("kw", "error"),
    [
        ({"channels": (0,)}, "An archive takes the whole recording with all its channels."),
        ({"start_unix": T0 + 1}, "An archive takes the whole recording with all its channels."),
    ],
)
def test_archive_needs_the_whole_recording(env, kw, error):
    preview = env.preview(env.request(**kw))
    assert error in preview.errors
    with pytest.raises(TransferError):
        env.run(preview)
    assert env.transfers() == []


def test_archive_needs_a_folder_that_matches_the_entry(env):
    (env.source / "0" / f"{int(T0) + 3}.dat").write_bytes(bytes(4000))
    preview = env.preview(env.request())
    (error,) = preview.errors
    assert error.startswith("The folder differs from the database entry.")
    assert "the folder holds 6 files, the database lists 5" in error


def test_archive_refuses_a_destination_another_recording_uses(env, make_recording):
    other = recording_from(
        make_recording(n_slots=2), site_id=1, storage_root=str(env.nas), rel_path="taken"
    )
    write_transaction(env.db, lambda c: repo.insert_recording(c, other))
    preview = env.preview(env.request(dest=env.nas / "taken"))
    assert "Recording 2 is already logged at the destination folder." in preview.errors


def test_archive_of_an_archived_recording_is_refused(env):
    env.run(env.preview(env.request()))
    preview = env.preview(env.request(dest=env.nas / "again"))
    assert "The recording is already archived." in preview.errors


def test_archive_outside_the_nas_is_refused(env):
    preview = env.preview(env.request(dest=env.tmp / "pc" / "rec"))
    assert any(
        e.startswith("An archive goes to a folder in one of the NAS") for e in preview.errors
    )


def test_two_archives_at_once_keep_the_first(env):
    """Two people archive one recording to two folders; the second finish is refused."""
    first = env.preview(env.request(dest=env.nas / "first"))
    second = env.preview(env.request(dest=env.nas / "second"))
    assert first.ok and second.ok
    assert env.run(first).passed
    out = env.run(second)
    assert out.verification is Verification.FAIL
    assert out.notes.startswith("Someone else archived this recording")
    assert env.recording().rel_path == "first"
    rows = env.transfers()
    assert [r.verification for r in rows] == [Verification.PASS, Verification.FAIL]
    assert rows[1].finished_at is not None


def test_a_failed_check_leaves_the_recording_local(env):
    preview = env.preview(env.request())
    dest = Path(preview.request.destination)
    first = preview.selection.files[0]

    def corrupt_at_end(p: CopyProgress) -> None:
        if p.files_done == p.files_total:
            local_path(dest, first.rel_path).write_bytes(b"\xff" * first.size)

    out = env.run(preview, copy_progress=corrupt_at_end)
    assert out.verification is Verification.FAIL
    assert out.notes == (
        f"The check failed for 1 file: {first.rel_path} (The content differs from the "
        "source (SHA-256).)"
    )
    assert env.recording().archive_state is ArchiveState.LOCAL
    assert not env.manifests.exists()


def test_a_cancelled_archive_is_recorded_and_can_resume(env):
    calls = itertools.count()
    out = env.run(env.preview(env.request()), cancelled=lambda: next(calls) > 8)
    assert out.verification is Verification.SKIPPED
    assert out.notes.startswith("Cancelled after ")
    assert env.recording().archive_state is ArchiveState.LOCAL

    again = env.preview(env.request())
    assert again.ok, again.errors
    assert again.check.existing
    out = env.run(again)
    assert out.passed
    assert set(out.copy.skipped) == set(again.check.existing)
    first, second = env.transfers()
    assert (first.verification, second.verification) == (Verification.SKIPPED, Verification.PASS)
    assert env.recording().archive_state is ArchiveState.ARCHIVED


def test_a_file_already_in_place_with_other_content_fails_the_archive(env):
    """D63: a same-size file from outside the app is hashed, even outside the sample."""
    request = env.request(hash_mode=HashMode.SAMPLE)
    preview = env.preview(request)
    files = preview.selection.files
    sample = hash_targets([f.rel_path for f in files], HashMode.SAMPLE, 0.25)
    stranger = next(f for f in files if f.rel_path not in sample)
    dest = Path(preview.destination)
    target = local_path(dest, stranger.rel_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xff" * stranger.size)
    again = env.preview(request)
    assert again.ok, again.errors
    assert again.check.existing == {stranger.rel_path}
    out = env.run(again)
    assert out.verification is Verification.FAIL
    assert stranger.rel_path in out.notes
    assert env.recording().archive_state is ArchiveState.LOCAL


def test_the_estimate_counts_reading_the_skipped_files(env):
    request = env.request(hash_mode=HashMode.SAMPLE)
    preview = env.preview(request)
    assert preview.hashed_files == 3  # ceil(0.25 * 10)
    dest = Path(preview.destination)
    in_place = [f.rel_path for f in preview.selection.files[:4]]
    for rel in in_place:
        target = local_path(dest, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(local_path(env.source, rel).read_bytes())
    again = env.preview(request)
    paths = [f.rel_path for f in again.selection.files]
    hashed = len(hash_targets(paths, HashMode.SAMPLE, 0.25) | set(in_place))
    assert again.hashed_files == hashed
    speed = env.config.network_speed_mb_s * 1e6
    # destination reads of every hashed file, plus source reads of the files in place
    assert again.estimate.hash_s == pytest.approx((hashed + len(in_place)) * 4000 / speed)


# ---------------------------------------------------------------------------
# Deleting the laptop copy
# ---------------------------------------------------------------------------


def archived(env) -> int:
    out = env.run(env.preview(env.request()))
    assert out.passed
    return out.transfer_id


def test_delete_after_a_passed_archive(env):
    archive_id = archived(env)
    out = delete_laptop_copy(env.db, archive_id, performed_by="userB", now=env.now)
    assert out.result.complete
    assert not env.source.exists()
    _, delete = env.transfers()
    assert delete.operation is Operation.DELETE
    assert delete.parent_id == archive_id
    assert delete.verification is Verification.PASS
    assert (delete.n_files, delete.total_bytes) == (10, 40_000)
    assert delete.notes == "Deleted 10 files from the laptop."
    rows = viewer.transfer_rows(env.transfers(), 8.0)
    assert [r.operation for r in rows] == ["Archive", "Delete laptop copy"]
    assert rows[1].result.endswith("deleted")


def test_an_archive_typed_with_a_mapped_drive_uses_the_nas_location(env):
    """The log row, the manifest and the recording name one folder, so delete works."""
    request = env.request(dest=f"Z:\\2026\\{env.source.name}")
    preview = env.preview(request, resolve_drive=lambda d: str(env.nas) if d == "Z:" else None)
    assert preview.ok, preview.errors
    nas_folder = str(env.nas / "2026" / env.source.name)
    assert preview.destination == nas_folder
    archive_id = env.run(preview).transfer_id
    (row,) = env.transfers()
    assert row.destination == nas_folder
    assert read_manifest(Path(row.manifest_path)).destination == nas_folder
    out = delete_laptop_copy(env.db, archive_id, performed_by="userB", now=env.now)
    assert out.result.complete


def test_delete_keeps_files_whose_nas_copy_changed(env):
    archive_id = archived(env)
    rec = env.recording()
    nas_folder = Path(rec.storage_root) / rec.rel_path
    (nas_folder / "1" / f"{int(T0)}.dat").write_bytes(b"x")
    out = delete_laptop_copy(env.db, archive_id, performed_by="userB", now=env.now)
    assert not out.result.complete
    delete = env.transfers()[-1]
    assert delete.verification is Verification.FAIL
    assert delete.n_files == 9
    assert delete.notes == (
        "Deleted 9 files from the laptop. Kept 1 file: 1/1790733600.dat (The NAS copy is "
        "missing or has another size.)"
    )
    assert (env.source / "1" / f"{int(T0)}.dat").exists()


def test_delete_needs_a_passed_archive(env):
    preview = env.preview(env.request(Operation.COPY, env.tmp / "pc" / "rec"))
    copy_id = env.run(preview).transfer_id
    with pytest.raises(DeleteRefused, match="Only the laptop copy"):
        delete_laptop_copy(env.db, copy_id, performed_by="userB", now=env.now)
    assert env.source.exists()
    assert len(env.transfers()) == 1


def test_delete_refuses_a_changed_manifest(env):
    archive_id = archived(env)
    manifest = Path(env.transfers()[0].manifest_path)
    manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(DeleteRefused, match="changed after it was written"):
        delete_laptop_copy(env.db, archive_id, performed_by="userB", now=env.now)
    assert len(tree(env.source)) == 10
    assert len(env.transfers()) == 1


def test_delete_refuses_when_the_recording_points_elsewhere(env):
    archive_id = archived(env)
    write_transaction(
        env.db,
        lambda c: repo.update_archive_location(
            c,
            env.rid,
            storage_root=str(env.nas),
            rel_path="elsewhere",
            archived_at="2026-10-04T00:00:00Z",
        ),
    )
    with pytest.raises(DeleteRefused, match="no longer points at the archive copy"):
        delete_laptop_copy(env.db, archive_id, performed_by="userB", now=env.now)
    assert len(tree(env.source)) == 10


# ---------------------------------------------------------------------------
# Check archive
# ---------------------------------------------------------------------------


def test_check_of_a_good_archive_passes(env):
    archived(env)
    out = check_archive(env.db, env.rid, performed_by="userC", now=env.now)
    assert out.verification is Verification.PASS
    check = env.transfers()[-1]
    assert check.operation is Operation.CHECK
    assert check.destination is None
    assert (check.n_files, check.total_bytes) == (10, 40_000)
    assert check.hash_mode is HashMode.NONE


def test_check_finds_a_difference(env):
    archived(env)
    rec = env.recording()
    (Path(rec.storage_root) / rec.rel_path / "0" / f"{int(T0) + 3}.dat").write_bytes(bytes(4000))
    out = check_archive(env.db, env.rid, performed_by="userC", now=env.now)
    assert out.verification is Verification.FAIL
    assert out.notes == "Channel 0: the folder holds 6 files, the database lists 5."


def test_check_fills_in_missing_counts(env):
    archived(env)
    write_transaction(
        env.db, lambda c: c.execute("UPDATE channels SET n_files = NULL, total_bytes = NULL")
    )
    out = check_archive(env.db, env.rid, performed_by="userC", now=env.now)
    assert out.verification is Verification.SKIPPED
    assert [(c.n_files, c.total_bytes) for c in env.recording().channels] == [
        (5, 20_000),
        (5, 20_000),
    ]


def test_check_of_a_missing_folder_fails(env):
    archived(env)
    write_transaction(
        env.db,
        lambda c: repo.update_archive_location(
            c,
            env.rid,
            storage_root=str(env.nas),
            rel_path="gone",
            archived_at="2026-10-04T00:00:00Z",
        ),
    )
    out = check_archive(env.db, env.rid, performed_by="userC", now=env.now)
    assert out.verification is Verification.FAIL
    assert out.notes.startswith("Cannot scan the folder: folder not found")


def test_check_needs_an_archived_recording(env):
    with pytest.raises(TransferError, match="Only an archived recording"):
        check_archive(env.db, env.rid, performed_by="userC", now=env.now)
    assert env.transfers() == []
