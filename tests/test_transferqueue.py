"""The Archive / copy queue (DECISIONS.md D81).

The list logic runs without files. run_item() copies, verifies and checks real files,
all under tmp_path: two "laptop" recordings from make_fixtures and a "NAS" folder
given to Config directly. No network path is used.
"""

import itertools
from dataclasses import replace
from pathlib import Path

import pytest

from conftest import recording_from
from iqdm import transferqueue
from iqdm.config import Config
from iqdm.db import repository as repo
from iqdm.db.connection import DatabaseBusyError, DatabaseError, open_db, write_transaction
from iqdm.models import ArchiveState, HashMode, Operation, Verification
from iqdm.transfer.copier import CopyProgress
from iqdm.transfer.delete import DeleteRefused
from iqdm.transfer.operations import CHECK_NEEDS_HASHES, TransferRequest
from iqdm.transfer.pathcheck import DiskUsage
from iqdm.transferqueue import (
    ItemResult,
    Phase,
    QueueError,
    QueueItem,
    QueueKind,
    QueueState,
    TransferQueue,
    item_for_recording,
    preview_item,
    run_item,
    scope_text,
    state_text,
)

OPTIONS = {
    "resolve_drive": None,
    "disk_usage": lambda _p: DiskUsage(10**15, 0, 10**15),
    "long_paths": True,
}


def request(rid: int, dest: str, operation=Operation.ARCHIVE, **kw) -> TransferRequest:
    return TransferRequest(
        recording_id=rid, operation=operation, destination=dest, hash_mode=HashMode.ALL, **kw
    )


def item(rid: int, dest: str = "", kind=QueueKind.ARCHIVE, **kw) -> QueueItem:
    req = None if kind is QueueKind.CHECK_ARCHIVE else request(rid, dest or f"D:\\n\\{rid}")
    return QueueItem(recording_id=rid, label=f"Recording {rid}", kind=kind, request=req, **kw)


# ---------------------------------------------------------------------------
# The list
# ---------------------------------------------------------------------------


def test_items_keep_their_order_and_get_keys():
    queue = TransferQueue()
    a, b = queue.add(item(1)), queue.add(item(2))
    c = queue.add(item(3), position=0)
    assert [i.recording_id for i in queue.items] == [3, 1, 2]
    assert len({a.key, b.key, c.key}) == 3
    assert queue.position(b.key) == 2
    assert queue.next_runnable() == c


def test_an_active_repeat_is_refused():
    queue = TransferQueue()
    queue.add(item(1, "D:\\nas\\a"))
    with pytest.raises(QueueError, match="already in the queue"):
        queue.add(item(1, "D:\\nas\\b"))
    with pytest.raises(QueueError, match="already goes to"):
        queue.add(item(2, "d:\\NAS\\a\\"))  # the same folder, written otherwise
    queue.add(item(1, kind=QueueKind.CHECK_ARCHIVE))  # another operation is fine
    with pytest.raises(QueueError, match="already in the queue"):
        queue.add(item(1, kind=QueueKind.CHECK_ARCHIVE))


def test_two_copies_of_one_recording_to_two_folders_are_allowed():
    """Channel 0 to one folder and channel 1 to another, for example."""
    queue = TransferQueue()
    first = replace(
        item(7, kind=QueueKind.COPY),
        request=request(7, "C:\\pc\\ch0", Operation.COPY, channels=(0,)),
    )
    second = replace(first, request=request(7, "C:\\pc\\ch1", Operation.COPY, channels=(1,)))
    queue.add(first)
    queue.add(second)
    assert len(queue) == 2
    with pytest.raises(QueueError, match="already goes to"):
        queue.add(replace(first, request=request(7, "c:\\PC\\ch0", Operation.COPY)))


def test_holding_finds_the_item_a_form_run_would_repeat():
    """D86: the form does not run a transfer that the queue holds."""
    queue = TransferQueue()
    archive = queue.add(item(1, "D:\\nas\\a"))
    copy = queue.add(
        replace(item(2, kind=QueueKind.COPY), request=request(2, "C:\\pc\\x", Operation.COPY))
    )
    assert queue.holding(request(1, "D:\\nas\\elsewhere")) == archive  # the same archive
    assert queue.holding(request(2, "c:\\PC\\x\\", Operation.COPY)) == copy  # the same folder
    assert queue.holding(request(2, "C:\\pc\\y", Operation.COPY)) is None  # another copy
    assert queue.holding(request(3, "D:\\nas\\b")) is None
    queue.set_state(archive.key, QueueState.DONE)
    assert queue.holding(request(1, "D:\\nas\\a")) is None  # finished items do not hold


def test_has_paused():
    queue = TransferQueue()
    first = queue.add(item(1))
    assert not queue.has_paused()
    queue.set_state(first.key, QueueState.PAUSED)
    assert queue.has_paused()


def test_a_finished_item_may_be_added_again():
    queue = TransferQueue()
    first = queue.add(item(1))
    queue.set_result(first.key, ItemResult(state=QueueState.FAILED, note="x"))
    queue.add(item(1))
    assert len(queue) == 2


def test_the_running_item_cannot_be_removed():
    queue = TransferQueue()
    running = queue.add(item(1))
    waiting = queue.add(item(2))
    queue.set_state(running.key, QueueState.RUNNING)
    with pytest.raises(QueueError, match="Pause the queue first"):
        queue.remove(running.key)
    queue.remove(waiting.key)
    assert [i.recording_id for i in queue.items] == [1]


def test_paused_items_run_first_in_their_place():
    queue = TransferQueue()
    done, paused, waiting = queue.add(item(1)), queue.add(item(2)), queue.add(item(3))
    queue.set_state(done.key, QueueState.DONE)
    queue.set_state(paused.key, QueueState.PAUSED)
    assert queue.next_runnable().key == paused.key
    assert queue.runnable_count() == 2
    queue.set_state(paused.key, QueueState.NOT_STARTED)
    assert queue.next_runnable().key == waiting.key
    assert queue.clear_finished() == 2
    assert [i.key for i in queue.items] == [waiting.key]


def test_a_result_keeps_a_size_and_id_it_lacks():
    queue = TransferQueue()
    added = queue.add(item(1, size_bytes=500))
    queue.set_result(added.key, ItemResult(state=QueueState.PAUSED, note="p", transfer_id=4))
    queue.set_result(added.key, ItemResult(state=QueueState.DONE, note="ok"))
    got = queue.get(added.key)
    assert (got.size_bytes, got.transfer_id, got.state) == (500, 4, QueueState.DONE)
    assert state_text(got) == "Done: ok"


def test_scope_text():
    assert scope_text(item(1), 8.0) == "Whole recording"
    ranged = replace(
        item(1),
        request=request(1, "D:\\x", Operation.COPY, channels=(0, 2), start_unix=0.0, end_unix=60.0),
    )
    assert (
        scope_text(ranged, 0.0)
        == "Ch 0, 2 \N{MIDDLE DOT} 1970-01-01 00:00:00 to 1970-01-01 00:01:00"
    )
    assert scope_text(item(1, kind=QueueKind.CHECK_ARCHIVE), 0.0) == (
        "NAS folder against the catalogue"
    )


# ---------------------------------------------------------------------------
# Items from the Viewer
# ---------------------------------------------------------------------------


def test_a_laptop_recording_is_archived_into_the_nas_folder(make_recording):
    rec = recording_from(make_recording(), id=5, site_id=1, created_at="2026-10-23T08:00:00Z")
    got = item_for_recording(
        rec,
        check_archive_only=False,
        nas_folder="D:\\nas\\2026",
        config=Config(),
        hash_mode=HashMode.SAMPLE,
        label="r5",
    )
    assert got.kind is QueueKind.ARCHIVE
    assert got.request == TransferRequest(
        recording_id=5,
        operation=Operation.ARCHIVE,
        destination=f"D:\\nas\\2026\\{rec.rel_path}",
        hash_mode=HashMode.SAMPLE,
    )
    assert got.created_at == "2026-10-23T08:00:00Z"  # the entry it was made for (O52)
    with pytest.raises(QueueError, match="Choose the NAS folder"):
        item_for_recording(
            rec,
            check_archive_only=False,
            nas_folder=" ",
            config=Config(),
            hash_mode=HashMode.ALL,
            label="",
        )
    with pytest.raises(QueueError, match="not archived"):
        item_for_recording(
            rec,
            check_archive_only=True,
            nas_folder="",
            config=Config(),
            hash_mode=HashMode.ALL,
            label="",
        )


def test_an_archived_recording_is_copied_to_the_copy_folder(make_recording):
    rec = replace(
        recording_from(make_recording(), id=6, site_id=1),
        archive_state=ArchiveState.ARCHIVED,
        archived_at="2026-10-01T00:00:00Z",
        rel_path="2026\\rec6",
    )
    config = Config(default_local_copy_root="C:\\copies")
    got = item_for_recording(
        rec,
        check_archive_only=False,
        nas_folder="",
        config=config,
        hash_mode=HashMode.ALL,
        label="",
    )
    assert (got.kind, got.destination) == (QueueKind.COPY, "C:\\copies\\2026\\rec6")
    assert got.request.operation is Operation.COPY
    with pytest.raises(QueueError, match="no default copy folder"):
        item_for_recording(
            rec,
            check_archive_only=False,
            nas_folder="",
            config=Config(),
            hash_mode=HashMode.ALL,
            label="",
        )
    check = item_for_recording(
        rec,
        check_archive_only=True,
        nas_folder="",
        config=Config(),
        hash_mode=HashMode.ALL,
        label="",
    )
    assert (check.kind, check.request) == (QueueKind.CHECK_ARCHIVE, None)


# ---------------------------------------------------------------------------
# Running items, on real files under tmp_path
# ---------------------------------------------------------------------------


class Env:
    def __init__(self, tmp_path: Path, db_path: Path, infos) -> None:
        self.tmp = tmp_path
        self.db = db_path
        self.nas = tmp_path / "nas"
        self.nas.mkdir()
        self.manifests = tmp_path / "app" / "manifests"
        self.config = Config(nas_roots=(str(self.nas),), hash_sample_fraction=0.25, copy_workers=1)
        self.infos = infos

        def insert(conn):
            site = repo.add_site(conn, "SiteA").id
            return [repo.insert_recording(conn, recording_from(i, site_id=site)) for i in infos]

        self.rids = write_transaction(db_path, insert)

    def item(self, n: int = 0, *, dest: Path | None = None, operation=Operation.ARCHIVE, **kw):
        rid = self.rids[n]
        folder = dest or self.nas / Path(self.infos[n].root).name
        kind = QueueKind.ARCHIVE if operation is Operation.ARCHIVE else QueueKind.COPY
        return QueueItem(
            recording_id=rid,
            label=f"Recording {rid}",
            kind=kind,
            request=TransferRequest(
                recording_id=rid,
                operation=operation,
                destination=str(folder),
                hash_mode=kw.pop("hash_mode", HashMode.ALL),
            ),
            **kw,
        )

    def run(self, it: QueueItem, *, check_after=True, cancelled=lambda: False, report=None):
        seen: list[object] = []
        result = run_item(
            self.db,
            it,
            self.config,
            performed_by="userA",
            manifests_dir=self.manifests,
            check_after_archive=check_after,
            report=report or seen.append,
            cancelled=cancelled,
            preview_options=OPTIONS,
        )
        return result, seen

    def recording(self, n: int = 0):
        with open_db(self.db, readonly=True) as conn:
            return repo.get_recording(conn, self.rids[n])

    def transfers(self, n: int = 0):
        with open_db(self.db, readonly=True) as conn:
            return repo.list_transfers(conn, self.rids[n])


@pytest.fixture
def env(tmp_path, db_path, make_recording) -> Env:
    infos = [make_recording(n_channels=2, n_slots=6), make_recording(n_slots=4)]
    return Env(tmp_path, db_path, infos)


def test_an_archive_with_its_check_before_delete(env):
    result, seen = env.run(env.item())
    assert result.state is QueueState.DONE
    assert "Check before delete passed" in result.note
    assert result.size_bytes == sum(c.total_bytes for c in env.infos[0].channels)
    assert env.recording().archive_state is ArchiveState.ARCHIVED
    archive, check = env.transfers()
    assert (archive.operation, archive.verification) == (Operation.ARCHIVE, Verification.PASS)
    assert (check.operation, check.parent_id, check.verification) == (
        Operation.CHECK,
        archive.id,
        Verification.PASS,
    )
    phases = [p.text for p in seen if isinstance(p, Phase)]
    assert phases == [
        "Scanning the source folder",
        "Copying",
        "Check before delete: reading the NAS copy",
    ]


def test_an_archive_without_the_check(env):
    result, _ = env.run(env.item(), check_after=False)
    assert result.state is QueueState.DONE
    assert [t.operation for t in env.transfers()] == [Operation.ARCHIVE]


def test_sizes_only_skips_the_check_and_says_why(env):
    """D85: the archive passed, so it is not Failed; its laptop copy cannot go yet."""
    result, _ = env.run(env.item(hash_mode=HashMode.NONE))
    assert result.state is QueueState.CHECK_NEEDED
    assert result.note.startswith("Archived: transfer ")
    assert CHECK_NEEDS_HASHES in result.note
    assert result.note.endswith(
        "Run Check before delete in the form; the laptop copy can be deleted only after "
        "it passes."
    )
    assert [t.operation for t in env.transfers()] == [Operation.ARCHIVE]
    assert env.recording().archive_state is ArchiveState.ARCHIVED


def test_a_failed_check_before_delete_is_check_needed(env, monkeypatch):
    """The check found a NAS file that differs: the archive still stands (D85)."""
    real = transferqueue.check_before_delete

    def spoil_then_check(db, archive_id, **kw):
        dest = env.nas / Path(env.infos[0].root).name
        first = sorted(dest.rglob("*.dat"))[0]
        first.write_bytes(b"\xff" * first.stat().st_size)  # same size, other content
        return real(db, archive_id, **kw)

    monkeypatch.setattr(transferqueue, "check_before_delete", spoil_then_check)
    item = env.item(hash_mode=HashMode.ALL)
    result, _ = env.run(item)
    assert result.state is QueueState.CHECK_NEEDED
    assert "Check before delete failed:" in result.note
    assert env.recording().archive_state is ArchiveState.ARCHIVED
    archive, check = env.transfers()
    assert (archive.verification, check.verification) == (Verification.PASS, Verification.FAIL)


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (OSError(87, "The parameter is incorrect"), "The parameter is incorrect"),
        (DeleteRefused(["The archive copy has no file list."]), "has no file list"),
        # A locked catalogue after a passed archive (review of 1.1.0, finding 1)
        (DatabaseBusyError("The database is in use by someone else."), "in use by someone"),
        (DatabaseError("disk I/O error"), "disk I/O error"),
        (RuntimeError("unexpected"), "unexpected"),
    ],
)
def test_a_check_that_cannot_run_is_check_needed(env, monkeypatch, error, reason):
    def fail(*_a, **_kw):
        raise error

    monkeypatch.setattr(transferqueue, "check_before_delete", fail)
    result, _ = env.run(env.item())
    assert result.state is QueueState.CHECK_NEEDED
    assert "Check before delete could not run:" in result.note
    assert reason in result.note


def test_a_stopped_check_before_delete_is_check_needed(env, monkeypatch):
    real = transferqueue.check_before_delete
    monkeypatch.setattr(
        transferqueue,
        "check_before_delete",
        lambda db, aid, **kw: real(db, aid, **(kw | {"cancelled": lambda: True})),
    )
    result, _ = env.run(env.item())
    assert result.state is QueueState.CHECK_NEEDED
    assert "Check before delete was stopped." in result.note


def test_clear_finished_keeps_archives_whose_check_is_needed():
    queue = TransferQueue()
    done, needed, failed = queue.add(item(1)), queue.add(item(2)), queue.add(item(3))
    queue.set_state(done.key, QueueState.DONE)
    queue.set_state(needed.key, QueueState.CHECK_NEEDED)
    queue.set_state(failed.key, QueueState.FAILED)
    assert queue.next_runnable() is None  # Start skips it
    assert queue.clear_finished() == 2
    assert [i.key for i in queue.items] == [needed.key]
    queue.remove(needed.key)  # Remove takes it out
    assert len(queue) == 0


def test_a_copy_and_a_check_archive(env):
    dest = env.tmp / "pc" / "copy"
    copied, _ = env.run(env.item(1, dest=dest, operation=Operation.COPY))
    assert copied.state is QueueState.DONE
    assert len(list(dest.rglob("*.dat"))) == env.infos[1].channels[0].n_files
    env.run(env.item(1))  # archive it, so Check archive applies
    check = QueueItem(recording_id=env.rids[1], label="r", kind=QueueKind.CHECK_ARCHIVE)
    result, seen = env.run(check)
    assert result.state is QueueState.DONE
    assert Phase("Check archive: scanning the NAS folder") in seen
    assert env.transfers(1)[-1].operation is Operation.CHECK


def test_a_failed_preview_is_not_started(env):
    outside = env.tmp / "elsewhere" / "rec"  # not under a NAS location
    result, _ = env.run(env.item(dest=outside))
    assert result.state is QueueState.NOT_STARTED
    assert result.note
    assert env.transfers() == []
    assert not outside.exists()


REUSED_AT = "2026-10-23T09:00:00Z"


def replace_newest(env: Env, info) -> int:
    """Another PC deletes the newest entry and logs another folder; the new entry gets
    the deleted entry's number (O52). The two are logged a second apart."""

    def swap(conn) -> int:
        repo.delete_recording(conn, env.rids[-1])
        rid = repo.insert_recording(conn, recording_from(info, site_id=1))
        conn.execute("UPDATE recordings SET created_at = ? WHERE id = ?", (REUSED_AT, rid))
        return rid

    return write_transaction(env.db, swap)


def test_an_item_does_not_run_for_an_entry_that_took_its_number(env, make_recording):
    it = env.item(1, created_at=env.recording(1).created_at)
    assert replace_newest(env, make_recording(n_slots=3)) == env.rids[1]
    result, seen = env.run(it)
    assert result.state is QueueState.NOT_STARTED
    assert result.note == (
        f"Recording {env.rids[1]} is no longer the entry this queue item was made for. That "
        "entry was deleted, and a new entry got its number. Remove this item."
    )
    assert seen == []
    assert env.transfers(1) == []
    assert not (env.nas / Path(env.infos[1].root).name).exists()


def test_a_check_archive_item_is_checked_the_same_way(env, make_recording):
    created = env.recording(1).created_at
    replace_newest(env, make_recording(n_slots=3))
    check = QueueItem(
        recording_id=env.rids[1], label="r", kind=QueueKind.CHECK_ARCHIVE, created_at=created
    )
    result, _ = env.run(check)
    assert result.state is QueueState.NOT_STARTED
    assert env.transfers(1) == []


def test_an_item_for_a_deleted_entry_is_not_started(env):
    it = env.item(1, created_at=env.recording(1).created_at)
    write_transaction(env.db, lambda conn: repo.delete_recording(conn, env.rids[1]))
    result, _ = env.run(it)
    assert result.state is QueueState.NOT_STARTED
    assert result.note == repo.gone_text(env.rids[1])


def test_an_item_for_its_own_entry_runs(env):
    result, _ = env.run(env.item(created_at=env.recording().created_at), check_after=False)
    assert result.state is QueueState.DONE
    assert transferqueue.entry_problem(env.db, env.item(created_at=None)) is None


def test_a_pause_stops_the_item_and_resume_continues_it(env):
    """D81: a cancel finishes the row as skipped; the next run skips the copied files."""
    stop = {"now": False}

    def report(value: object) -> None:
        if isinstance(value, CopyProgress) and value.files_done >= 1:
            stop["now"] = True

    paused, _ = env.run(env.item(), cancelled=lambda: stop["now"], report=report)
    assert paused.state is QueueState.PAUSED
    assert "Resume continues it" in paused.note
    (row,) = env.transfers()
    assert row.verification is Verification.SKIPPED
    assert env.recording().archive_state is ArchiveState.LOCAL
    dest = env.nas / Path(env.infos[0].root).name
    copied = sorted(p.name for p in dest.rglob("*.dat"))
    assert 0 < len(copied) < 12

    done, _ = env.run(env.item())
    assert done.state is QueueState.DONE
    assert env.recording().archive_state is ArchiveState.ARCHIVED
    assert len(list(dest.rglob("*.dat"))) == 12


def test_a_pause_before_the_copy(env):
    result, _ = env.run(env.item(), cancelled=lambda: True)
    assert result.state is QueueState.PAUSED
    assert result.note == "Paused before the copy started."
    assert env.transfers() == []


def test_preview_item_finds_size_and_problems(env):
    ok = preview_item(env.db, env.item(), env.config, preview_options=OPTIONS)
    assert (ok.state, ok.note) == (QueueState.WAITING, "")
    assert ok.size_bytes and ok.size_bytes > 0
    bad = preview_item(
        env.db, env.item(dest=env.tmp / "elsewhere"), env.config, preview_options=OPTIONS
    )
    assert bad.state is QueueState.WAITING
    assert bad.note
    assert not (env.tmp / "elsewhere").exists()


def test_a_queue_runs_items_in_turn(env):
    """Two archives one after another, as the tab runs them."""
    queue = TransferQueue()
    for n in (0, 1):
        queue.add(env.item(n))
    ticks = itertools.count()
    while (it := queue.next_runnable()) is not None:
        next(ticks)
        queue.set_state(it.key, QueueState.RUNNING)
        result, _ = env.run(it)
        queue.set_result(it.key, result)
    assert next(ticks) == 2
    assert [i.state for i in queue.items] == [QueueState.DONE, QueueState.DONE]
    assert env.recording(0).archive_state is ArchiveState.ARCHIVED
    assert env.recording(1).archive_state is ArchiveState.ARCHIVED
