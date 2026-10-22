"""Deleting a catalogue entry added by mistake (DECISIONS.md D89). Data lives in tmp_path.

The delete removes catalogue rows only. Every test that deletes also checks that the
recording's files keep their names, sizes and modification times.
"""

import json
from pathlib import Path

import pytest

from conftest import recording_from
from iqdm import entry
from iqdm.db import repository as repo
from iqdm.db.connection import open_db, write_transaction
from iqdm.deletion_record import FORMAT, DeletionRecordError, record_name
from iqdm.models import Operation, Recording, TransferEntry, Verification

NOW = "2026-10-23T08:00:00Z"


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Each file under root, with its size and modification time in nanoseconds."""
    return {
        p.relative_to(root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def logged(db_path, info, **kw) -> Recording:
    """The entry as edit mode opens it."""

    def insert(conn):
        site = repo.add_site(conn, f"Site{info.root[-1]}").id
        return repo.insert_recording(conn, recording_from(info, site_id=site, **kw))

    rid = write_transaction(db_path, insert)
    return stored(db_path, rid)


def stored(db_path, rid: int) -> Recording:
    with open_db(db_path, readonly=True) as conn:
        return repo.get_recording(conn, rid)


def rows(db_path, rid: int) -> list[TransferEntry]:
    with open_db(db_path, readonly=True) as conn:
        return repo.list_transfers(conn, rid)


def add_row(db_path, rid: int, operation=Operation.CHECK, **kw) -> int:
    values = {
        "recording_id": rid,
        "operation": operation,
        "source": "//nas/recordings/rec",
        "started_at": NOW,
        "finished_at": NOW,
        "performed_by": "tester",
    } | kw
    return write_transaction(
        db_path, lambda conn: repo.insert_transfer(conn, TransferEntry(**values))
    )


def in_place(db_path, rid: int) -> None:
    write_transaction(
        db_path,
        lambda conn: repo.insert_in_place_check(
            conn, rid, source="//nas/recordings/rec", performed_by="tester", at=NOW
        ),
    )


@pytest.fixture
def records(tmp_path) -> Path:
    return tmp_path / "app" / "deleted-entries"


def test_an_entry_without_history_is_deleted_and_its_files_stay(db_path, make_recording, records):
    info = make_recording(n_channels=2)
    before = snapshot(Path(info.root))
    original = logged(db_path, info)
    check = entry.check_deletion(db_path, original)
    assert check.transfers == []
    path = entry.delete_entry(db_path, check, records_folder=records, deleted_by="userB", now=NOW)
    assert path == records / record_name(original.id, NOW)
    with pytest.raises(repo.NotFoundError):
        stored(db_path, original.id)
    assert snapshot(Path(info.root)) == before
    data = json.loads(path.read_text(encoding="utf-8"))
    assert (data["format"], data["version"]) == (FORMAT, 1)
    assert (data["deleted_at"], data["deleted_by"]) == (NOW, "userB")
    assert data["database"] == str(db_path)
    assert data["recording"]["id"] == original.id
    assert data["recording"]["rel_path"] == original.rel_path
    assert [c["channel_index"] for c in data["recording"]["channels"]] == [0, 1]
    assert data["transfers"] == []


def test_an_entry_logged_in_place_goes_with_its_check_rows(db_path, make_recording, records):
    info, other_info = make_recording(), make_recording()
    before = snapshot(Path(info.root))
    original = logged(db_path, info)
    other = logged(db_path, other_info)
    in_place(db_path, original.id)
    add_row(db_path, original.id, verification=Verification.PASS)  # a Check archive
    in_place(db_path, other.id)
    check = entry.check_deletion(db_path, original)
    question = entry.delete_question(check, 8.0, records)
    assert "Its 2 check results are deleted with it." in question
    path = entry.delete_entry(db_path, check, records_folder=records, deleted_by="u", now=NOW)
    assert len(json.loads(path.read_text(encoding="utf-8"))["transfers"]) == 2
    assert rows(db_path, original.id) == []
    assert len(rows(db_path, other.id)) == 1
    assert stored(db_path, other.id).id == other.id
    assert snapshot(Path(info.root)) == before


@pytest.mark.parametrize("operation", [Operation.COPY, Operation.ARCHIVE])
def test_an_archive_or_a_copy_keeps_the_entry(db_path, make_recording, records, operation):
    original = logged(db_path, make_recording())
    add_row(db_path, original.id, operation, destination="D:/work/rec")
    with pytest.raises(repo.HasTransferHistoryError, match="archive or a copy"):
        entry.check_deletion(db_path, original)
    assert not records.exists()
    assert stored(db_path, original.id).id == original.id


def test_an_entry_changed_since_it_was_opened_is_refused(db_path, make_recording, records):
    original = logged(db_path, make_recording())
    write_transaction(
        db_path,
        lambda conn: conn.execute(
            "UPDATE recordings SET remarks = 'changed' WHERE id = ?", (original.id,)
        ),
    )
    with pytest.raises(repo.RecordingChangedError, match="then delete it"):
        entry.check_deletion(db_path, original)
    assert not records.exists()


def test_a_change_after_the_question_deletes_nothing(db_path, make_recording, records):
    """Another PC copies the recording between the question and the delete."""
    original = logged(db_path, make_recording())
    check = entry.check_deletion(db_path, original)
    add_row(db_path, original.id, Operation.COPY, destination="D:/work/rec")
    with pytest.raises(entry.EntryNotDeletedError) as caught:
        entry.delete_entry(db_path, check, records_folder=records, deleted_by="u", now=NOW)
    path = records / record_name(original.id, NOW)
    assert str(path) in str(caught.value)
    assert "was not deleted" in str(caught.value)
    assert path.exists()  # the copy saved before the attempt stays
    assert stored(db_path, original.id).id == original.id
    assert len(rows(db_path, original.id)) == 1


def test_an_entry_deleted_on_another_pc(db_path, make_recording, records):
    original = logged(db_path, make_recording())
    check = entry.check_deletion(db_path, original)
    entry.delete_entry(db_path, check, records_folder=records, deleted_by="u", now=NOW)
    with pytest.raises(repo.NotFoundError, match="no longer in the catalogue"):
        entry.check_deletion(db_path, original)
    with pytest.raises(entry.EntryNotDeletedError, match="no longer in the catalogue"):
        entry.delete_entry(
            db_path, check, records_folder=records, deleted_by="u", now="2026-10-23T08:00:01Z"
        )


def test_a_save_over_a_deleted_entry_says_so(db_path, make_recording, records):
    original = logged(db_path, make_recording())
    check = entry.check_deletion(db_path, original)
    entry.delete_entry(db_path, check, records_folder=records, deleted_by="u", now=NOW)
    with pytest.raises(repo.NotFoundError, match="It may have been deleted on another PC"):
        entry.save_edit(db_path, original, original=original)


def test_an_existing_record_is_kept_and_nothing_is_deleted(db_path, make_recording, records):
    original = logged(db_path, make_recording())
    records.mkdir(parents=True)
    path = records / record_name(original.id, NOW)
    path.write_text("someone else's file", encoding="utf-8")
    check = entry.check_deletion(db_path, original)
    with pytest.raises(DeletionRecordError, match="already exists"):
        entry.delete_entry(db_path, check, records_folder=records, deleted_by="u", now=NOW)
    assert path.read_text(encoding="utf-8") == "someone else's file"
    assert stored(db_path, original.id).id == original.id


def test_the_question_names_the_folder_start_and_files(db_path, make_recording, records):
    info = make_recording(n_channels=2, n_slots=3)
    original = logged(db_path, info)
    question = entry.delete_question(entry.check_deletion(db_path, original), 8.0, records)
    assert question.startswith(f"Delete recording {original.id} from the catalogue?\n\n")
    assert f"Folder: {Path(info.root)}" in question
    assert "Start: 2026-09-30 10:00:00 UTC+8" in question
    assert "2 channels, 6 files" in question
    assert "The files in the folder are not touched." in question
    assert "check result" not in question
    assert str(records) in question
