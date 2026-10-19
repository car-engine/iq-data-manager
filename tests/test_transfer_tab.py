"""GUI tests for the Archive / copy tab (SPEC section 8).

Every recording, NAS folder, PC folder and manifest lives under tmp_path. The "NAS"
is a tmp_path folder given to Config(nas_roots=...). Previews get stubs for the
drive mapping, the free space and the long-path setting, as in test_operations.py.
Modal dialogs are replaced with stubs that record their text and answer.
"""

import time
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QFileDialog, QMessageBox

import iqdm.gui.transfer_tab as tab_module
from conftest import recording_from
from iqdm import transferqueue, viewer
from iqdm.config import Config
from iqdm.db import repository as repo
from iqdm.db.connection import open_db, write_transaction
from iqdm.entry import ItemState
from iqdm.gui.transfer_tab import TransferTab
from iqdm.gui.widgets.checklist import DARK_COLOURS, LIGHT_COLOURS
from iqdm.models import IN_PLACE_NOTE, ArchiveState, HashMode, Operation, TransferEntry
from iqdm.movecopy import LaptopStep
from iqdm.transfer.copier import CopyItem, copy_files
from iqdm.transfer.delete import DeleteResult, KeptFile
from iqdm.transfer.manifest import read_manifest
from iqdm.transfer.operations import FILE_LIST_UNUSABLE, DeleteOutcome, TransferRequest
from iqdm.transfer.pathcheck import DiskUsage
from iqdm.transferqueue import QueueItem, QueueKind, QueueState
from make_fixtures import ChannelSpec

T0 = 1790733600.0
STUBS = {
    "resolve_drive": None,
    "disk_usage": lambda _p: DiskUsage(10**15, 0, 10**15),
    "long_paths": True,
}


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class Answers:
    """QMessageBox.question replaced: records each text and gives the next answer."""

    def __init__(self, monkeypatch) -> None:
        self.texts: list[str] = []
        self.next = QMessageBox.StandardButton.No

        def question(parent, title, text, *args, **kwargs):
            self.texts.append(text)
            return self.next

        monkeypatch.setattr(QMessageBox, "question", question)


@pytest.fixture
def answers(monkeypatch) -> Answers:
    return Answers(monkeypatch)


class Env:
    def __init__(self, qtbot, tmp_path: Path, db_path: Path, info) -> None:
        self.qtbot = qtbot
        self.tmp = tmp_path
        self.db = db_path
        self.info = info
        self.source = Path(info.root)
        self.nas = tmp_path / "nas"
        self.nas.mkdir()
        self.pc = tmp_path / "pc"
        self.manifests = tmp_path / "app" / "manifests"
        self.config = Config(
            db_path=str(db_path),
            nas_roots=(str(self.nas),),
            default_local_copy_root=str(self.pc),
            hash_sample_fraction=0.25,
            display_utc_offset_hours=8,
        )

        def insert(conn):
            site = repo.add_site(conn, "SiteA").id
            return repo.insert_recording(conn, recording_from(info, site_id=site))

        self.rid = write_transaction(db_path, insert)
        self.tabs: list[TransferTab] = []

    def tab(self, **kw) -> TransferTab:
        values = {
            "manifests_dir": self.manifests,
            "performed_by": lambda: "userA",
            "preview_options": STUBS,
        } | kw
        tab = TransferTab(self.config, **values)
        self.qtbot.addWidget(tab)
        self.tabs.append(tab)
        self.idle(tab)
        return tab

    def idle(self, tab: TransferTab, timeout: int = 20_000) -> None:
        self.qtbot.waitUntil(lambda: not tab.runner.busy, timeout=timeout)

    def loaded(self, tab: TransferTab, rid: int | None = None) -> TransferTab:
        assert tab.load_recording(self.rid if rid is None else rid)
        self.idle(tab)
        assert tab.recording is not None
        return tab

    def transfers(self, rid: int | None = None) -> list[TransferEntry]:
        with open_db(self.db, readonly=True) as conn:
            return repo.list_transfers(conn, self.rid if rid is None else rid)

    def recording(self):
        with open_db(self.db, readonly=True) as conn:
            return repo.get_recording(conn, self.rid)

    def previewed(self, tab: TransferTab) -> None:
        tab.preview_button.click()
        self.idle(tab)
        assert tab.preview is not None, [i.text for i in tab.preview_lines.items]

    def ran(self, tab: TransferTab) -> None:
        assert tab.run_button.isEnabled()
        tab.run_button.click()
        self.idle(tab, 60_000)


@pytest.fixture
def env(qtbot, tmp_path, db_path, make_recording):
    info = make_recording(n_channels=2, n_slots=6, channels={1: ChannelSpec(gaps=frozenset({3}))})
    e = Env(qtbot, tmp_path, db_path, info)
    yield e
    for tab in e.tabs:
        tab.stop(ask=False)
        tab.wait_until_idle(20_000)


def archive_to_nas(env: Env, tab: TransferTab) -> Path:
    tab.archive_radio.setChecked(True)
    dest = env.nas / "2026" / env.source.name
    tab.dest_edit.setText(str(dest))
    env.previewed(tab)
    env.ran(tab)
    return dest


# ---------------------------------------------------------------------------
# Loading and the form
# ---------------------------------------------------------------------------


def test_without_a_database_the_tab_says_where_to_set_it(qtbot, tmp_path):
    tab = TransferTab(Config(), manifests_dir=tmp_path / "m")
    qtbot.addWidget(tab)
    assert tab.message_label.text().endswith("Set the database path in the Settings tab.")
    assert not tab.preview_button.isEnabled()
    assert not tab.load_recording(1)


def test_a_saved_database_path_clears_the_no_database_line(env):
    """Found in the user's manual test: the line stayed after Save in Settings."""
    tab = env.tab(manifests_dir=env.manifests)
    tab.apply_config(Config())
    assert not tab.message_label.isHidden()
    tab.apply_config(env.config)
    env.idle(tab)
    assert tab.message_label.isHidden()
    assert tab.message_label.text() == ""
    assert tab.load_recording(env.rid)
    env.idle(tab)
    assert tab.recording is not None


def test_loading_a_local_recording_prepares_an_archive(env):
    tab = env.loaded(env.tab())
    assert tab.archive_radio.isChecked()
    assert tab.run_button.text() == "Run archive"
    assert tab.whole_radio.isChecked() and not tab.range_radio.isEnabled()
    assert sorted(tab.channel_boxes) == [0, 1]
    assert all(b.isChecked() and not b.isEnabled() for b in tab.channel_boxes.values())
    assert tab.dest_edit.text() == ""
    assert tab.source_label.text().startswith(f"{env.rid} \N{MIDDLE DOT} 2026-09-30 10:00:00")
    assert not tab.run_button.isEnabled()  # no preview yet
    assert tab.laptop_label.text() == (
        "The recording is on the laptop. Archive it to the NAS first."
    )


def test_the_recording_line_names_its_project(env):
    """D73: the project follows the site; a recording without one shows none."""
    tab = env.loaded(env.tab())
    assert "Radar Trial" not in tab.source_label.text()

    def tag(conn) -> None:
        project = repo.add_project(conn, "Radar Trial").id
        conn.execute("UPDATE recordings SET project_id = ? WHERE id = ?", (project, env.rid))

    write_transaction(env.db, tag)
    tab = env.loaded(env.tab())
    assert " \N{MIDDLE DOT} SiteA \N{MIDDLE DOT} Radar Trial \N{MIDDLE DOT} " in (
        tab.source_label.text()
    )


def test_a_copy_fills_in_the_local_copy_folder(env):
    """D60: the local copy folder and the recording's relative path."""
    tab = env.loaded(env.tab())
    tab.copy_radio.setChecked(True)
    assert tab.dest_edit.text() == str(env.pc / env.source.name)
    assert tab.run_button.text() == "Run copy"
    assert tab.range_radio.isEnabled()


def test_time_fields_read_the_display_offset_and_stay_in_sync(env):
    """D59."""
    tab = env.loaded(env.tab())
    tab.copy_radio.setChecked(True)
    tab.range_radio.setChecked(True)
    assert tab.from_label.text() == "From (UTC+8)"
    assert tab.from_edit.text() == "2026-09-30 10:00:00"
    assert tab.from_unix_edit.text() == "1790733600"
    tab.from_edit.setText("2026-09-30 10:00:02")
    tab.from_edit.editingFinished.emit()
    assert tab.from_unix_edit.text() == "1790733602"
    tab.to_unix_edit.setText("1790733604.5")
    tab.to_unix_edit.editingFinished.emit()
    assert tab.to_edit.text() == "2026-09-30 10:00:04.5"
    tab.from_edit.setText("tomorrow")
    tab.from_edit.editingFinished.emit()
    assert tab.time_error_label.text() == (
        "\N{BALLOT X} From: Write the time as YYYY-MM-DD HH:MM:SS."
    )
    tab.preview_button.click()
    env.idle(tab)
    assert tab.preview is None
    assert [i.text for i in tab.preview_lines.items] == [
        "From: Write the time as YYYY-MM-DD HH:MM:SS."
    ]


# ---------------------------------------------------------------------------
# Preview and copy
# ---------------------------------------------------------------------------


def test_preview_then_copy_a_range_of_one_channel(env):
    tab = env.loaded(env.tab())
    changed: list[int] = []
    tab.recording_changed.connect(changed.append)
    tab.copy_radio.setChecked(True)
    tab.range_radio.setChecked(True)
    tab.from_unix_edit.setText(str(int(T0) + 1))
    tab.from_unix_edit.editingFinished.emit()
    tab.to_unix_edit.setText(str(int(T0) + 5))
    tab.to_unix_edit.editingFinished.emit()
    tab.channel_boxes[0].setChecked(False)
    env.previewed(tab)
    assert tab.files_value.text() == "3"
    assert tab.missing_value.text() == "Channel 1: 1 missing second"
    assert tab.timeline.selection == (T0 + 1, T0 + 5, frozenset({"Ch 1"}))
    env.ran(tab)
    dest = env.pc / env.source.name
    assert sorted(tree(dest)) == [f"1/{int(T0) + i}.dat" for i in (1, 2, 4)]
    assert tab.result[0] is ItemState.OK
    assert tab.result[1].startswith("The copy passed its check.")
    (row,) = env.transfers()
    assert row.operation is Operation.COPY
    assert changed == [env.rid]
    assert not tab.is_busy and tab.progress_bar.isHidden()


@pytest.mark.parametrize("mode", [HashMode.NONE, HashMode.SAMPLE, HashMode.ALL])
def test_the_hash_mode_reaches_the_transfer_as_a_hash_mode(env, mode):
    """QComboBox keeps a StrEnum as plain text; the request must hold the HashMode."""
    tab = env.loaded(env.tab())
    tab.copy_radio.setChecked(True)
    tab.hash_combo.setCurrentIndex(tab.hash_combo.findData(mode))
    assert tab.hash_mode() is mode
    env.previewed(tab)
    assert tab.preview.request.hash_mode is mode
    env.ran(tab)
    (row,) = env.transfers()
    assert row.hash_mode is mode
    hashed = len(read_manifest(Path(row.manifest_path)).files) - sum(
        1 for f in read_manifest(Path(row.manifest_path)).files if not f.sha256
    )
    assert hashed == {HashMode.NONE: 0, HashMode.SAMPLE: 3, HashMode.ALL: 11}[mode]


def test_a_change_to_the_form_drops_the_preview(env):
    tab = env.loaded(env.tab())
    tab.copy_radio.setChecked(True)
    env.previewed(tab)
    assert tab.run_button.isEnabled()
    tab.dest_edit.setText(str(env.pc / "elsewhere"))
    tab.dest_edit.textEdited.emit(tab.dest_edit.text())
    assert tab.preview is None
    assert not tab.run_button.isEnabled()


def test_preview_errors_block_the_run(env):
    tab = env.loaded(env.tab())
    tab.dest_edit.setText(str(env.tmp / "not-the-nas"))
    env.previewed(tab)
    assert not tab.preview.ok
    assert tab.preview_lines.items[0].state is ItemState.ERROR
    assert not tab.run_button.isEnabled()


# ---------------------------------------------------------------------------
# Archive, check before delete, delete (D55)
# ---------------------------------------------------------------------------


def test_archive_check_and_delete(env, answers):
    tab = env.loaded(env.tab())
    dest = archive_to_nas(env, tab)
    assert tab.result[1].endswith("The recording now points at the NAS copy.")
    assert env.recording().archive_state is ArchiveState.ARCHIVED
    env.idle(tab)
    assert tab.laptop_state().step is LaptopStep.CHECK_NEEDED
    assert tab.check_delete_button.isEnabled()
    assert not tab.delete_button.isEnabled()

    tab.check_delete_button.click()
    env.idle(tab)
    assert tab.result[0] is ItemState.OK
    assert tab.laptop_state().step is LaptopStep.READY
    assert tab.delete_button.isEnabled()

    answers.next = QMessageBox.StandardButton.No
    tab.delete_button.click()
    env.idle(tab)
    assert len(tree(env.source)) == 11  # No deletes nothing
    assert answers.texts[-1].startswith(f"Delete the laptop copy of recording {env.rid}?")
    assert f"in {env.source} will be deleted. The NAS copy in {dest} stays." in answers.texts[-1]

    answers.next = QMessageBox.StandardButton.Yes
    tab.delete_button.click()
    env.idle(tab)
    assert not env.source.exists()
    assert tab.result == (ItemState.OK, "Deleted 11 files from the laptop.")
    assert tab.laptop_state().step is LaptopStep.DELETED
    assert not tab.delete_button.isEnabled()


def test_a_changed_file_list_is_refused_in_plain_words(env):
    tab = env.loaded(env.tab())
    archive_to_nas(env, tab)
    env.idle(tab)
    manifest = Path(env.transfers()[0].manifest_path)
    manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
    tab.check_delete_button.click()
    env.idle(tab)
    assert tab.result == (ItemState.ERROR, FILE_LIST_UNUSABLE)
    assert "changed after it was written" in tab.result_label.toolTip()


def test_delete_results_name_one_file_in_the_singular(env):
    tab = env.loaded(env.tab())
    result = DeleteResult(
        deleted=("0/1790733600.dat",),
        already_gone=(),
        kept=(KeptFile(rel_path="0/1790733601.dat", reason="The laptop file changed."),),
        folders_removed=(),
    )
    tab._delete_done(DeleteOutcome(transfer_id=1, result=result))
    env.idle(tab)
    assert tab.result == (
        ItemState.ERROR,
        "Deleted 1 file. Kept 1 file: 0/1790733601.dat: The laptop file changed.",
    )


def test_check_before_delete_needs_a_hash_mode_that_reads_content(env):
    tab = env.loaded(env.tab())
    archive_to_nas(env, tab)
    env.idle(tab)
    tab.hash_combo.setCurrentIndex(tab.hash_combo.findData(HashMode.NONE))
    tab.check_delete_button.click()
    env.idle(tab)
    assert tab.result[0] is ItemState.ERROR
    assert tab.result[1].startswith("Check before delete reads the content of the NAS files.")
    assert tab.laptop_state().step is LaptopStep.CHECK_NEEDED
    assert len(env.transfers()) == 1


def test_check_archive_from_the_tab(env):
    tab = env.loaded(env.tab())
    archive_to_nas(env, tab)
    env.idle(tab)
    assert tab.check_archive_button.isEnabled()
    tab.check_archive_button.click()
    env.idle(tab)
    assert tab.result == (ItemState.OK, "The folder matches the database entry.")


# ---------------------------------------------------------------------------
# Stop, resume, forget
# ---------------------------------------------------------------------------


@pytest.fixture
def slow(monkeypatch):
    """Slow the copy down to 0.1 s per chunk, so a test can stop it part-way."""
    real = tab_module.run_transfer

    def run_transfer(db, preview, **kw):
        report = kw["copy_progress"]

        def slowly(p):
            time.sleep(0.1)
            report(p)

        kw["copy_progress"] = slowly
        kw["workers"] = 1
        return real(db, preview, **kw)

    monkeypatch.setattr(tab_module, "run_transfer", run_transfer)


def start_and_wait_for_progress(env, tab):
    tab.run_button.click()
    env.qtbot.waitUntil(lambda: tab.progress_label.text().startswith("1 of"), timeout=10_000)
    assert tab.is_busy and not tab.stop_button.isHidden()


def test_stop_asks_first_and_the_run_can_resume(env, answers, slow):
    tab = env.loaded(env.tab())
    tab.copy_radio.setChecked(True)
    env.previewed(tab)
    statuses: list[str] = []
    tab.status_changed.connect(statuses.append)
    start_and_wait_for_progress(env, tab)
    assert not tab.preview_button.isEnabled() and not tab.dest_edit.isEnabled()

    answers.next = QMessageBox.StandardButton.No
    assert not tab.stop()
    assert tab.is_busy
    answers.next = QMessageBox.StandardButton.Yes
    assert tab.stop()
    assert "Files already copied stay in the destination." in answers.texts[-1]
    env.idle(tab)
    assert tab.result[0] is ItemState.TODO
    assert tab.result[1].startswith("Stopped after ")
    assert any(s.startswith("copying ") for s in statuses) and statuses[-1] == ""
    in_place = tree(env.pc / env.source.name)
    copied = sum(1 for p in in_place if not p.endswith(".partial"))  # complete files
    assert 0 < copied < 11

    env.idle(tab)
    (stopped,) = tab.unfinished
    assert stopped.operation is Operation.COPY
    assert tab.unfinished_table.item(0, 5).text().startswith("Stopped: Stopped after ")

    other = env.tab()  # another session, as after a restart of the app
    (row,) = other.unfinished
    assert row.id == stopped.id
    other.select_unfinished(0)
    other.resume_button.click()
    env.idle(other)
    assert other.preview is not None
    assert other.copy_radio.isChecked()
    assert len(other.preview.check.existing) == copied
    other.run_button.click()
    env.idle(other, 60_000)
    assert other.result[0] is ItemState.OK
    assert tree(env.pc / env.source.name) == tree(env.source)
    assert other.unfinished == []


def test_another_copy_can_run_before_the_resume(env, answers, slow, make_recording):
    tab = env.loaded(env.tab())
    tab.copy_radio.setChecked(True)
    env.previewed(tab)
    start_and_wait_for_progress(env, tab)
    answers.next = QMessageBox.StandardButton.Yes
    tab.stop()
    env.idle(tab)

    second = make_recording(n_slots=2)
    rid2 = write_transaction(
        env.db, lambda c: repo.insert_recording(c, recording_from(second, site_id=1))
    )
    env.loaded(tab, rid2)
    tab.copy_radio.setChecked(True)
    env.previewed(tab)
    env.ran(tab)
    assert tab.result[0] is ItemState.OK
    env.idle(tab)
    (left,) = tab.unfinished
    assert left.recording_id == env.rid


def test_forget_hides_a_stopped_copy_and_keeps_its_files(env, answers, slow):
    tab = env.loaded(env.tab())
    tab.copy_radio.setChecked(True)
    env.previewed(tab)
    start_and_wait_for_progress(env, tab)
    answers.next = QMessageBox.StandardButton.Yes
    tab.stop()
    env.idle(tab)
    files = tree(env.pc / env.source.name)
    tab.select_unfinished(0)
    answers.next = QMessageBox.StandardButton.No
    tab.forget_button.click()
    env.idle(tab)
    assert len(tab.unfinished) == 1
    answers.next = QMessageBox.StandardButton.Yes
    tab.forget_button.click()
    env.idle(tab)
    assert "Delete that folder by hand if you no longer need it." in answers.texts[-1]
    assert tab.unfinished == []
    assert tree(env.pc / env.source.name) == files
    assert env.transfers()[0].dismissed_at is not None


def test_other_users_are_listed_on_request(env, answers, slow):
    tab = env.loaded(env.tab())
    tab.copy_radio.setChecked(True)
    env.previewed(tab)
    start_and_wait_for_progress(env, tab)
    answers.next = QMessageBox.StandardButton.Yes
    tab.stop()
    env.idle(tab)
    other_user = env.tab(performed_by=lambda: "userB")
    assert other_user.unfinished == []
    other_user.others_check.setChecked(True)
    env.idle(other_user)
    assert len(other_user.unfinished) == 1


# ---------------------------------------------------------------------------
# Compare with laptop copy (D56)
# ---------------------------------------------------------------------------


def logged_in_place(env) -> int:
    folder = env.nas / "in-place"
    items = [CopyItem(rel_path=p, size=len(b)) for p, b in tree(env.source).items()]
    assert copy_files(env.source, folder, items).ok

    def insert(conn):
        rec = recording_from(
            env.info,
            site_id=1,
            storage_root=str(env.nas),
            rel_path="in-place",
            archive_state=ArchiveState.ARCHIVED,
            archived_at="2026-10-03T07:00:00Z",
        )
        rid = repo.insert_recording(conn, rec)
        repo.insert_transfer(
            conn,
            TransferEntry(
                recording_id=rid,
                operation=Operation.CHECK,
                source=str(folder),
                started_at="2026-10-03T07:00:00Z",
                finished_at="2026-10-03T07:00:00Z",
                performed_by="userA",
                notes=IN_PLACE_NOTE,
            ),
        )
        return rid

    return write_transaction(env.db, insert)


def test_compare_with_laptop_copy_clears_the_mark(env, monkeypatch):
    rid = logged_in_place(env)
    tab = env.loaded(env.tab(), rid)
    assert tab.copy_radio.isChecked() and not tab.archive_radio.isEnabled()
    assert not tab.compare_button.isHidden() and tab.compare_button.isEnabled()
    assert "Not verified." in tab.laptop_label.text()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(env.source))
    tab.hash_combo.setCurrentIndex(tab.hash_combo.findData(HashMode.ALL))
    tab.compare_button.click()
    env.idle(tab)
    assert tab.result[0] is ItemState.OK
    assert tab.result[1].startswith("The NAS folder matches the laptop folder")
    env.idle(tab)
    assert tab.compare_button.isHidden()
    rows = env.transfers(rid)
    assert not viewer.is_unverified(tab.recording, rows)


def test_compare_is_offered_only_for_a_recording_not_verified(env):
    tab = env.loaded(env.tab())
    assert tab.compare_button.isHidden()


# ---------------------------------------------------------------------------
# Queue (D81)
# ---------------------------------------------------------------------------


def second_recording(env: Env, make_recording) -> int:
    info = make_recording(n_slots=4)

    def insert(conn):
        site = repo.find_site(conn, "SiteA").id
        return repo.insert_recording(conn, recording_from(info, site_id=site))

    return write_transaction(env.db, insert)


def queue_idle(env: Env, tab: TransferTab, timeout: int = 60_000) -> None:
    env.qtbot.waitUntil(lambda: not tab.queue_running and not tab.runner.busy, timeout=timeout)


def states(tab: TransferTab) -> list[QueueState]:
    return [i.state for i in tab.queue]


def queued_from_viewer(env: Env, tab: TransferTab, *rids: int) -> None:
    tab.queue_nas_edit.setText(str(env.nas / "2026"))
    tab.add_recordings(list(rids))
    env.idle(tab)


@pytest.fixture
def slow_queue(monkeypatch):
    """Slow the queue's copy down to 0.1 s per file report, with one file at a time."""
    real = transferqueue.run_transfer

    def run_transfer(db, preview, **kw):
        report = kw["copy_progress"]

        def slowly(p):
            time.sleep(0.1)
            report(p)

        kw["copy_progress"] = slowly
        kw["workers"] = 1
        return real(db, preview, **kw)

    monkeypatch.setattr(transferqueue, "run_transfer", run_transfer)


def test_add_to_queue_from_the_form(env):
    tab = env.loaded(env.tab())
    assert tab.archive_radio.isChecked()
    tab.dest_edit.setText(str(env.nas / "2026" / env.source.name))
    assert not tab.add_queue_button.isEnabled()  # a preview comes first
    env.previewed(tab)
    assert tab.add_queue_button.isEnabled()
    tab.add_queue_button.click()
    (item,) = tab.queue
    assert (item.kind, item.state) == (QueueKind.ARCHIVE, QueueState.WAITING)
    assert item.recording_id == env.rid
    assert item.size_bytes == tab.preview.selection.total_bytes
    assert tab.result[1].startswith("Added to the queue: Recording")
    assert tab.queue_table.item(0, 1).text() == "Waiting"
    assert tab.queue_table.item(0, 2).text() == "Archive"
    assert tab.queue_table.item(0, 4).text() == "Whole recording"
    tab.add_queue_button.click()  # the same recording again
    assert len(tab.queue) == 1
    assert tab.result == (ItemState.ERROR, f"Recording {env.rid} is already in the queue for this.")
    assert env.transfers() == []  # nothing ran


def test_start_runs_the_items_in_turn(env, make_recording):
    other = second_recording(env, make_recording)
    tab = env.tab()
    queued_from_viewer(env, tab, env.rid, other)
    assert states(tab) == [QueueState.WAITING, QueueState.WAITING]
    assert all(i.size_bytes for i in tab.queue)  # previewed when added
    statuses: list[str] = []
    tab.status_changed.connect(statuses.append)
    busy: list[bool] = []
    tab.busy_changed.connect(busy.append)
    tab.start_queue_button.click()
    assert tab.is_busy and not tab.start_queue_button.isEnabled()
    queue_idle(env, tab)
    assert states(tab) == [QueueState.DONE, QueueState.DONE]
    assert all("Check before delete passed" in i.note for i in tab.queue)
    assert env.recording().archive_state is ArchiveState.ARCHIVED
    assert any(s.startswith("queue 2 of 2") for s in statuses)
    assert busy[0] is True and busy[-1] is False and False not in busy[:-1]
    assert tab.result == (ItemState.OK, "Queue finished. 2 done.")
    assert not tab.is_busy


def test_pause_then_start_finishes_the_item(env, answers, slow_queue, make_recording):
    tab = env.tab()
    queued_from_viewer(env, tab, env.rid)
    tab.start_queue_button.click()
    env.qtbot.waitUntil(lambda: tab.progress_label.text().startswith("1 of"), timeout=10_000)
    assert tab.stop_button.isHidden()  # the queue pauses instead
    answers.next = QMessageBox.StandardButton.No
    tab.pause_queue_button.click()
    assert tab.queue_running and states(tab) == [QueueState.RUNNING]
    answers.next = QMessageBox.StandardButton.Yes
    tab.pause_queue_button.click()
    assert answers.texts[-1] == tab_module.PAUSE_QUEUE_QUESTION
    queue_idle(env, tab)
    assert states(tab) == [QueueState.PAUSED]
    assert tab.result[0] is ItemState.INFO and tab.result[1].startswith("Queue paused. 1 left")
    (stopped,) = tab.unfinished
    assert stopped.operation is Operation.ARCHIVE

    tab.start_queue_button.click()
    queue_idle(env, tab)
    assert states(tab) == [QueueState.DONE]
    assert env.recording().archive_state is ArchiveState.ARCHIVED
    assert tab.unfinished == []


def test_a_waiting_item_can_be_removed_while_the_queue_runs(env, slow_queue, make_recording):
    other = second_recording(env, make_recording)
    tab = env.tab()
    queued_from_viewer(env, tab, env.rid, other)
    tab.start_queue_button.click()
    env.qtbot.waitUntil(lambda: tab.progress_label.text().startswith("1 of"), timeout=10_000)
    tab.select_queue_row(0)
    assert not tab.remove_queue_button.isEnabled()  # the running item
    tab.select_queue_row(1)
    assert tab.remove_queue_button.isEnabled()
    tab.remove_queue_button.click()
    queue_idle(env, tab)
    assert [(i.recording_id, i.state) for i in tab.queue] == [(env.rid, QueueState.DONE)]
    with open_db(env.db, readonly=True) as conn:
        assert repo.list_transfers(conn, other) == []


def test_a_failed_item_does_not_stop_the_queue(env, make_recording):
    other = second_recording(env, make_recording)
    tab = env.tab()
    queued_from_viewer(env, tab, other)
    outside = QueueItem(
        recording_id=env.rid,
        label="first",
        kind=QueueKind.ARCHIVE,
        request=TransferRequest(
            recording_id=env.rid,
            operation=Operation.ARCHIVE,
            destination=str(env.tmp / "not-the-nas" / "rec"),
            hash_mode=HashMode.ALL,
        ),
    )
    tab._queue.add(outside, position=0)
    tab.start_queue_button.click()
    queue_idle(env, tab)
    assert states(tab) == [QueueState.NOT_STARTED, QueueState.DONE]
    assert tab.queue[0].note
    tab.select_queue_row(0)
    assert tab.queue_note.text() == f"first: Not started: {tab.queue[0].note}"
    assert tab.queue_table.item(0, 1).toolTip() == f"Not started: {tab.queue[0].note}"
    assert tab.result[0] is ItemState.OK
    assert tab.result[1] == "Queue finished. 1 done, 1 not started."
    tab.clear_queue_button.click()
    assert tab.queue == []


def test_edit_puts_the_item_back_in_its_place(env, make_recording):
    other = second_recording(env, make_recording)
    tab = env.tab()
    queued_from_viewer(env, tab, env.rid, other)
    other_destination = tab.queue[1].destination
    tab.select_queue_row(0)
    tab.edit_queue_button.click()
    env.idle(tab)
    assert [i.recording_id for i in tab.queue] == [other]
    assert tab.recording.id == env.rid
    assert tab.archive_radio.isChecked()
    assert tab.preview is not None  # previewed again for the user
    new = env.nas / "elsewhere" / env.source.name
    tab.dest_edit.setText(str(new))
    env.previewed(tab)
    tab.add_queue_button.click()
    assert [(i.recording_id, i.destination) for i in tab.queue] == [
        (env.rid, str(new)),
        (other, other_destination),
    ]
    assert tab.message_label.text() == ""


def test_viewer_items_need_a_nas_folder_and_an_archive_to_check(env):
    tab = env.tab()
    tab.add_recordings([env.rid])
    env.idle(tab)
    assert tab.queue == []
    assert tab.result[0] is ItemState.ERROR
    assert "Choose the NAS folder for archives" in tab.result[1]
    tab.add_recordings([env.rid], check_archive=True)
    env.idle(tab)
    assert tab.queue == []
    assert "is not archived" in tab.result[1]


def test_check_archive_items(env):
    tab = env.loaded(env.tab())
    archive_to_nas(env, tab)
    tab.add_recordings([env.rid], check_archive=True)
    env.idle(tab)
    (item,) = tab.queue
    assert item.kind is QueueKind.CHECK_ARCHIVE
    assert tab.queue_table.item(0, 4).text() == "NAS folder against the catalogue"
    tab.start_queue_button.click()
    queue_idle(env, tab)
    assert states(tab) == [QueueState.DONE]
    assert env.transfers()[-1].operation is Operation.CHECK


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------


def dark_palette() -> QPalette:
    palette = QPalette()
    for role in (QPalette.ColorRole.Base, QPalette.ColorRole.Window):
        palette.setColor(role, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.Text, QColor(230, 230, 230))
    return palette


def test_result_colours_follow_the_palette(env):
    tab = env.loaded(env.tab())
    tab.copy_radio.setChecked(True)
    env.previewed(tab)
    env.ran(tab)
    light = LIGHT_COLOURS[ItemState.OK].name()
    assert f"color: {light}" in tab.result_label.styleSheet()
    assert tab.result_label.text().startswith("\N{CHECK MARK}")
    tab.setPalette(dark_palette())
    assert f"color: {DARK_COLOURS[ItemState.OK].name()}" in tab.result_label.styleSheet()
