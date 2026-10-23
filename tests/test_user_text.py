"""User-facing text holds no planning references or internals (CLAUDE.md, D38).

Walks the visible text of each tab: labels, buttons, group titles, placeholders,
table headings and tooltips. Decision numbers, SPEC sections, open items, config key
names and database internals belong in code comments and docs.
"""

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QAbstractItemModel, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTableView,
    QWidget,
)

import make_fixtures
from conftest import recording_from
from iqdm import batchlog, movecopy, recorderlog, templates, transferqueue
from iqdm.app import (
    CLEAR_LOG_TAB_QUESTION,
    CLOSE_QUESTION,
    LOG_TAB_SAVING,
    LOG_TAB_SAVING_EDIT,
    SETTINGS_UNSAVED_TAB,
    TRANSFER_BUSY,
    TRANSFER_RUNNING,
    UNSAVED_QUESTION,
    UNSAVED_WRONG_VALUE,
    folders_close_question,
    queue_close_question,
)
from iqdm.bands import BANDS
from iqdm.config import Config
from iqdm.db import repository as repo
from iqdm.db.connection import write_transaction
from iqdm.entry import (
    ChannelInput,
    DeletionCheck,
    EntryInput,
    ParamInput,
    changed_delete_text,
    changed_text,
    checklist,
    delete_question,
    deleted_text,
    kept_note,
    missing_channels_text,
)
from iqdm.gui.log_tab import (
    BAND_TOOLTIP,
    BATCH_TEMPLATE_CHANNELS_NOTE,
    BATCH_TEMPLATE_LOG_NOTE,
    CONFLICT_TITLE,
    DELETE_BUTTON,
    DELETE_TITLE,
    DELETE_TOOLTIP,
    DROP_FOLDERS_TITLE,
    KEEP_LOG_BUTTON,
    LOG_ROWS_HEADERS,
    LOG_ROWS_TOOLTIP,
    NO_FOLDER_SELECTED,
    NO_RECORDS_FOLDER,
    PARENT_IS_RECORDING,
    REPLACE_TEMPLATE_TITLE,
    SAVE_FOLDERS_TITLE,
    SEVERAL_TOOLTIP,
    TEMPLATE_FILTER,
    USE_TEMPLATE_BUTTON,
    LogTab,
    band_filled_tooltip,
    conflict_question,
    drop_folders_question,
    log_rows_note,
    log_rows_title,
    replace_template_question,
    save_button_text,
)
from iqdm.gui.log_tab import NO_PROJECT as LOG_NO_PROJECT
from iqdm.gui.settings_tab import SettingsTab, new_database_question
from iqdm.gui.transfer_tab import (
    PAUSE_QUEUE_QUESTION,
    QUEUE_EDIT_NOTE,
    QUEUE_HEADERS,
    QUEUE_HINT,
    QUEUE_NOTE_HINT,
    QUEUED_TEXT,
    TransferTab,
    queue_holds_text,
    tab_holds_text,
)
from iqdm.gui.viewer_tab import NO_PROJECT_FILTER, NO_PROJECT_TEXT, ViewerTab
from iqdm.gui.widgets.template_fields import TemplateFieldsDialog
from iqdm.models import (
    IN_PLACE_NOTE,
    ArchiveState,
    Channel,
    HashMode,
    Operation,
    Param,
    Recording,
    SampleType,
    TransferEntry,
)
from iqdm.scan.scanner import scan_recording
from iqdm.transfer.operations import FILE_LIST_UNUSABLE, TransferRequest, preview_transfer
from iqdm.transfer.pathcheck import DiskUsage
from make_fixtures import ChannelSpec

FORBIDDEN = re.compile(
    r"DECISIONS|\bSPEC\b|\bD\d{1,2}\b|\bO\d{1,2}\b|\bMilestone\b"
    r"|db_path|nas_roots|display_utc_offset_hours|coverage_highlight_percent|user_version"
    r"|default_local_copy_root|network_speed_mb_s|default_hash_mode|hash_sample_fraction"
    r"|free_space_margin_gb|copy_workers|transfer_log|parent_id"
    r"|schema|journal|busy timeout|foreign keys"
    r"|\bNAS roots?\b|manifest",  # the screen says "NAS locations" and "file list"
    re.IGNORECASE,
)


def model_texts(model: QAbstractItemModel) -> list[str]:
    """Headings, cell text and cell tooltips of a table model."""
    texts = []
    for col in range(model.columnCount()):
        texts.append(str(model.headerData(col, Qt.Orientation.Horizontal) or ""))
        for row in range(model.rowCount()):
            for role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
                texts.append(str(model.index(row, col).data(role) or ""))
    return texts


def visible_texts(root: QWidget, skip_tooltips: tuple[QWidget, ...] = ()) -> list[str]:
    texts: list[str] = []
    for widget in [root, *root.findChildren(QWidget)]:
        if isinstance(widget, QLabel | QAbstractButton):
            texts.append(widget.text())
        if isinstance(widget, QGroupBox):
            texts.append(widget.title())
        if isinstance(widget, QLineEdit):
            texts.append(widget.placeholderText())
        if isinstance(widget, QComboBox):
            texts.extend(widget.itemText(i) for i in range(widget.count()))
        if isinstance(widget, QTableView) and widget.model() is not None:  # and QTableWidget
            texts.extend(model_texts(widget.model()))
        if widget not in skip_tooltips:
            texts.append(widget.toolTip())
    return [t for t in texts if t]


def offending(texts: list[str]) -> list[str]:
    return [t for t in texts if FORBIDDEN.search(t)]


def test_forbidden_pattern_catches_the_old_texts():
    old = [
        "Database file (db_path)",
        "Displayed times only. The database stores UTC (DECISIONS.md D24).",
        "File found. Schema version 1, current. Journal mode delete.",
        "see SPEC section 4",
        "The folder is on a network share outside the configured NAS roots.",
        "The file list cannot be used: the manifest changed after it was written",
    ]
    assert offending(old) == old
    assert offending(["Connected. The database is ready to use.", "Show times at UTC offset"]) == []


@pytest.fixture
def settings_tab(qtbot, tmp_path, db_path):
    config = tmp_path / "config.toml"
    config.write_text(
        f"db_path = '{db_path}'\nnas_roots = ['\\\\nas\\recordings', 'D:\\data']\n",
        encoding="utf-8",
    )
    tab = SettingsTab(config)
    qtbot.addWidget(tab)
    qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)
    return tab


def test_settings_tab_text_is_plain(settings_tab):
    tab = settings_tab
    tab.offset_spin.setValue(5.1)  # shows the offset error too
    # The status line and problem line keep technical detail in their tooltips (D38).
    texts = visible_texts(tab, skip_tooltips=(tab.db_status, tab.problem_label))
    assert offending(texts) == []
    assert tab.roots_error.text()  # the wrong root's message was checked
    assert "New database..." in texts


def test_settings_tab_text_from_the_defaults_file_is_plain(qtbot, tmp_path):
    """The note and the problem line shown while the defaults file is read (D68)."""
    defaults = tmp_path / "defaults.toml"
    defaults.write_text("storage_roots = 5", encoding="utf-8")
    tab = SettingsTab(tmp_path / "config.toml", defaults_path=defaults)
    qtbot.addWidget(tab)
    qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)
    texts = visible_texts(tab, skip_tooltips=(tab.db_status, tab.problem_label))
    assert offending([t for t in texts if t != tab.problem_label.text()]) == []
    assert tab.defaults_note.text() in texts
    # The problem line names the wrong key, which only the file's owner can correct (D36).
    assert "storage_roots" in tab.problem_label.text()


def test_new_database_question_is_plain(tmp_path):
    """The Yes/No question of "New database..." is shown outside the tab (D67)."""
    assert offending([new_database_question(tmp_path / "project.db")]) == []


def test_project_text_is_plain():
    """The project choices in the Log tab and the Viewer (D73)."""
    texts = [LOG_NO_PROJECT, NO_PROJECT_FILTER, NO_PROJECT_TEXT, "Add project", "Project"]
    assert offending(texts) == []


def test_unsaved_settings_text_is_plain():
    """The tab title and the question about unsaved settings (D70)."""
    assert offending([SETTINGS_UNSAVED_TAB, UNSAVED_QUESTION, UNSAVED_WRONG_VALUE]) == []


def test_dialog_and_message_text_is_plain():
    """Questions and messages that appear outside a tab's widgets."""
    texts = [
        CLEAR_LOG_TAB_QUESTION,
        LOG_TAB_SAVING,
        LOG_TAB_SAVING_EDIT,
        TRANSFER_RUNNING,
        TRANSFER_BUSY,
        CLOSE_QUESTION,
        changed_text(12),  # an edit of an entry that changed meanwhile (D76)
        FILE_LIST_UNUSABLE,
    ]
    assert offending(texts) == []


def test_log_tab_text_is_plain(qtbot, db_path):
    tab = LogTab(Config(db_path=str(db_path)))
    qtbot.addWidget(tab)
    qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)
    texts = visible_texts(tab) + [item.text for item in tab.checklist.items]
    assert "Your name" in texts  # the placeholder of Logged by (D94)
    assert offending(texts) == []


def test_template_text_is_plain(qtbot, db_path, tmp_path):
    """The export dialog, the replace question and the import messages (D80)."""
    tab = LogTab(Config(db_path=str(db_path)))
    qtbot.addWidget(tab)
    qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)
    dialog = TemplateFieldsDialog(tab.template_field_rows())
    qtbot.addWidget(dialog)
    tpl = templates.LogTemplate(site="Hilltop", project="Survey", header_bytes=0)
    applied = templates.apply_template(EntryInput(), tpl, [], [])
    texts = [
        *visible_texts(dialog),
        dialog.windowTitle(),
        REPLACE_TEMPLATE_TITLE,
        replace_template_question(tmp_path / "usrp.toml"),
        templates.applied_text(tpl, applied.notes),
        TEMPLATE_FILTER,
        CONFLICT_TITLE,
        KEEP_LOG_BUTTON,
        USE_TEMPLATE_BUTTON,
        conflict_question(
            [
                recorderlog.Conflict("fc of channel 0", "300 MHz", "145.8 MHz"),
                recorderlog.Conflict("USRP gain", "30 dB", "no row"),
            ]
        ),
        "Template not loaded.",
    ]
    try:
        templates.write_template(tmp_path / "usrp.toml", tpl)
        (tmp_path / "usrp.toml.new").write_text("x", encoding="utf-8")
        templates.write_template(tmp_path / "usrp.toml", tpl)
    except templates.TemplateError as exc:
        texts.append(str(exc))
    for data in (
        {"site": "x"},
        {"format_version": 1},
        {"format_version": 1, "colour": 1},
        {"format_version": 1, "sample_type": "int12"},
        {"format_version": 1, "header_bytes": -1},
        {"format_version": 1, "channels": [{"band": "VHF"}]},
        {"format_version": 1, "rf_chain": [{"applies_to": "all"}]},
    ):
        try:
            templates.from_toml_data(data)
        except templates.TemplateError as exc:
            texts.append(str(exc))
    assert len(texts) > 12
    assert offending(texts) == []


def test_queue_text_is_plain():
    """The queue's questions, notes, states and the Viewer's menu (D81)."""
    item = transferqueue.QueueItem(
        recording_id=1, label="Recording 1", kind=transferqueue.QueueKind.CHECK_ARCHIVE
    )
    texts = [
        PAUSE_QUEUE_QUESTION,
        *QUEUED_TEXT.values(),
        "Resume",
        QUEUE_HINT,
        QUEUE_EDIT_NOTE,
        QUEUE_NOTE_HINT,
        *QUEUE_HEADERS,
        queue_close_question(1),
        queue_close_question(3),
        transferqueue.scope_text(item, 8.0),
        *(str(s) for s in transferqueue.QueueState),
        *(str(k) for k in transferqueue.QueueKind),
        "Archive or copy",
        "Check archive",
    ]
    assert offending(texts) == []


def test_recorder_log_text_is_plain(make_recording):
    """The checklist lines and the tooltip of values from the recorder's log (D82)."""
    log = recorderlog.RecorderLog(
        files=["x"],
        verdict="FAIL",
        pc_clock=True,
        gps_locked=False,
        restarts=2,
        stop_reason="error",
        files_written=99,
        problems=["cannot read recorder_x.log: Access is denied"],
    )
    scan = scan_recording(Path(make_recording().root), 1.0)
    items = recorderlog.checklist_items(log, scan, ("sample type int16", "USRP Gain"))
    passed = recorderlog.RecorderLog(files=["x"], verdict="PASS")
    pass_line = recorderlog.checklist_items(passed, None)
    texts = [i.text for i in items + pass_line] + [recorderlog.FROM_LOG_TOOLTIP]
    assert len(texts) == 10  # 8 lines, the pass line and the tooltip
    assert offending(texts) == []


def test_side_file_preview_line_is_plain(tmp_path, db_path, make_recording):
    """The preview line about the recorder's logs that a transfer takes along (D83)."""
    info = make_recording()
    (Path(info.root) / "log.txt").write_text("--channels 0\n", encoding="utf-8")
    nas = tmp_path / "nas"
    rid = write_transaction(
        db_path,
        lambda c: repo.insert_recording(
            c, recording_from(info, site_id=repo.add_site(c, "SiteA").id)
        ),
    )
    preview = preview_transfer(
        db_path,
        TransferRequest(
            recording_id=rid,
            operation=Operation.COPY,
            destination=str(tmp_path / "pc"),
            hash_mode=HashMode.SAMPLE,
        ),
        Config(nas_roots=(str(nas),)),
        resolve_drive=None,
        disk_usage=lambda _p: DiskUsage(10**15, 0, 10**15),
        long_paths=True,
    )
    lines = [i.text for i in movecopy.preview_summary(preview, 110).lines]
    also = [t for t in lines if t.startswith("Also copied")]
    assert also == [
        "Also copied: 1 file from the recording folder itself, such as the "
        "recorder's logs: log.txt."
    ]
    assert offending(also) == []


def test_kept_fields_text_is_plain():
    """The note and the message about values kept from the previous entry (D79)."""
    form = EntryInput(header_bytes=64, params=[ParamInput(param="SDR", value="X310")])
    texts = [
        kept_note(form, 2),
        missing_channels_text([1], True, 2),
        missing_channels_text([1, 2], False, 1),
    ]
    assert offending(texts) == []


def test_band_text_is_plain(make_recording):
    """The band box's tooltips and the line for an fc outside its band (D88)."""
    scan = scan_recording(Path(make_recording().root), 1.0)
    form = EntryInput(
        channels=[ChannelInput(channel_index=0, band="UHF", fc_mhz="145.8", fs_text="1k")]
    )
    lines = [i.text for i in checklist(form, scan=scan) if "outside" in i.text]
    assert lines == ["Channel 0: fc 145.8 MHz is outside UHF (300 to 1000 MHz). Check the band."]
    texts = [BAND_TOOLTIP, *lines, *(band_filled_tooltip(b) for b in BANDS)]
    assert offending(texts) == []


def test_several_folders_text_is_plain(qtbot, db_path, tmp_path, monkeypatch):
    """The "Several folders" mode with two scanned folders, its questions and messages (D90)."""
    parent = tmp_path / "session"
    for name in ("a", "b"):
        make_fixtures.make_recording(parent / name, make_fixtures.RecordingSpec())
    tab = LogTab(Config(db_path=str(db_path)))
    qtbot.addWidget(tab)
    qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)
    tab.several_radio.setChecked(True)
    tab.add_folders(parent)
    qtbot.waitUntil(lambda: not tab.runner.busy and len(tab.folders) == 2, timeout=10_000)
    qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)
    tab.refresh_checklist()
    texts = (
        visible_texts(tab)
        + [item.text for item in tab.checklist.items]
        + [item.text for item in tab.folder_checklist.items]
    )
    assert "Several folders" in texts
    views = tab._views
    names = {f.key: f.name for f, _ in views}
    texts += [
        SEVERAL_TOOLTIP,
        SAVE_FOLDERS_TITLE,
        DROP_FOLDERS_TITLE,
        NO_FOLDER_SELECTED,
        BATCH_TEMPLATE_CHANNELS_NOTE,
        BATCH_TEMPLATE_LOG_NOTE,
        PARENT_IS_RECORDING,
        drop_folders_question(3),
        save_button_text(3),
        folders_close_question(2),
        batchlog.save_question(views, site="A", project="", logged_by="u", offset_hours=8),
        batchlog.saved_text(
            [
                batchlog.SaveOutcome(views[0][0].key, recording_id=4),
                batchlog.SaveOutcome(views[1][0].key, error="the database is in use"),
            ],
            names,
        )[1],
        batchlog.combined_items([])[0].text,
        LOG_ROWS_TOOLTIP,
        *LOG_ROWS_HEADERS,
        log_rows_title("rec01"),
        log_rows_note(
            batchlog.LogShown(
                rows=(),
                replaced=(ParamInput(param="USRP gain", value="10", unit="dB"),),
                dtype=SampleType.INT8,
            ),
            SampleType.INT16,
        ),
    ]
    assert offending(texts) == []


def test_delete_text_is_plain(tmp_path):
    """The question, the messages and the refusals of a delete (D89)."""
    rec = Recording(
        id=12,
        logged_by="u",
        site_id=1,
        storage_root="C:/captures",
        rel_path="rec1",
        start_unix=1790733600,
        channels=[Channel(channel_index=0, fc_hz=145.8e6, fs_hz=1e3, start_unix=0, end_unix=1)],
    )
    check = DeletionCheck(recording=rec, transfers=[])
    texts = [
        DELETE_TITLE,
        DELETE_BUTTON,
        DELETE_TOOLTIP,
        NO_RECORDS_FOLDER,
        "Delete entry...",
        "Nothing deleted.",
        delete_question(check, 8.0, tmp_path / "deleted-entries"),
        deleted_text(12, tmp_path / "deleted-entries" / "recording-12.json"),
        changed_delete_text(12),
        repo.history_text(12),
        repo.gone_text(12),
        repo.reused_text(12, "preview"),
        repo.reused_text(12, "queue item"),
        queue_holds_text(12),
        tab_holds_text(12),
        "Recording 12 was deleted from the catalogue.",
    ]
    assert offending(texts) == []


def viewer_catalogue(db_path, info) -> tuple[int, int]:
    """A recording with gaps and a real folder, and one archived in place (not verified)."""
    root = Path(info.root)

    def fill(conn) -> tuple[int, int]:
        site = repo.add_site(conn, "SiteA").id
        chans = [
            Channel(
                channel_index=c.index,
                sub_path=c.sub_path,
                band="VHF",
                fc_hz=145.8e6,
                fs_hz=1000.0,
                start_unix=c.start_unix,
                end_unix=c.end_unix,
                n_files=c.n_files + 1,  # differs from the folder, so the scan reports it
                total_bytes=c.total_bytes,
            )
            for c in info.channels
        ]
        gappy = repo.insert_recording(
            conn,
            Recording(
                logged_by="userA",
                site_id=site,
                storage_root=str(root.parent),
                rel_path=root.name,
                channels=chans,
                params=[
                    Param(param="LNA gain", value="10", unit="dB"),
                    Param(param="LNA gain", value="20", unit="dB", channel_index=1),
                ],
            ),
        )
        archived = repo.insert_recording(
            conn,
            Recording(
                logged_by="userB",
                site_id=site,
                storage_root=r"\\nas\recordings",
                rel_path="full",
                channels=[
                    Channel(channel_index=0, fc_hz=1e6, fs_hz=1e3, start_unix=1.0, end_unix=2.0)
                ],
                archive_state=ArchiveState.ARCHIVED,
                archived_at="2026-10-01T05:00:00Z",
            ),
        )
        repo.insert_transfer(
            conn,
            TransferEntry(
                recording_id=archived,
                operation=Operation.CHECK,
                source=r"\\nas\recordings\full",
                started_at="2026-10-01T05:00:00Z",
                performed_by="userB",
                notes=IN_PLACE_NOTE,
            ),
        )
        return gappy, archived

    return write_transaction(db_path, fill)


def test_viewer_tab_text_is_plain(qtbot, db_path, make_recording):
    info = make_recording(n_channels=2, n_slots=20, channels={1: ChannelSpec(gaps=frozenset({3}))})
    gappy, archived = viewer_catalogue(db_path, info)
    tab = ViewerTab(Config(db_path=str(db_path)))
    qtbot.addWidget(tab)

    def idle() -> None:
        qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)

    idle()
    texts = visible_texts(tab)
    # The filter lists draw a summary in place of an entry (D78).
    texts += [c.summary() for c in (tab.site_combo, tab.project_combo, tab.band_combo)]
    tab.select_recording(archived)  # history and the not-verified note
    idle()
    texts += visible_texts(tab)
    tab.select_recording(gappy)
    idle()
    tab.channel_table.selectRow(1)  # an RF chain override
    tab.scan_button.click()  # gaps and a difference from the database
    idle()
    tab.start_from_edit.setText("wrong")
    tab.apply_button.click()  # a filter error
    texts += visible_texts(tab)
    assert tab.gap_label.text()
    assert tab.difference_label.text()
    assert tab.filter_error.text()
    assert offending(texts) == []


def test_transfer_tab_text_is_plain(qtbot, tmp_path, db_path, make_recording):
    info = make_recording(n_channels=2, n_slots=20, channels={1: ChannelSpec(gaps=frozenset({3}))})
    gappy, archived = viewer_catalogue(db_path, info)
    nas = tmp_path / "nas"
    config = Config(
        db_path=str(db_path), nas_roots=(str(nas),), default_local_copy_root=str(tmp_path / "pc")
    )
    tab = TransferTab(
        config,
        manifests_dir=tmp_path / "manifests",
        performed_by=lambda: "userA",
        preview_options={
            "resolve_drive": None,
            "disk_usage": lambda _p: DiskUsage(10**15, 0, 10**15),
            "long_paths": True,
        },
    )
    qtbot.addWidget(tab)

    def idle() -> None:
        qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)

    def texts_now() -> list[str]:
        return (
            visible_texts(tab)
            + [i.text for i in tab.preview_lines.items]
            + [tab.file_list.item(i).text() for i in range(tab.file_list.count())]
        )

    idle()
    texts = texts_now()
    tab.load_recording(gappy)  # a local recording with a gap: an archive
    idle()
    tab.dest_edit.setText(str(tmp_path / "not-on-the-nas"))
    tab.preview_button.click()  # archive errors: not on the NAS, folder differs
    idle()
    texts += texts_now()
    tab.copy_radio.setChecked(True)
    tab.preview_button.click()  # a copy preview with missing seconds and a difference
    idle()
    texts += texts_now()
    tab.range_radio.setChecked(True)
    tab.from_edit.setText("wrong")
    tab.from_edit.editingFinished.emit()  # a time error
    texts += texts_now()
    tab.load_recording(archived)  # not verified: the comparison and the laptop note
    idle()
    texts += texts_now()
    assert tab.preview_lines.items
    assert tab.laptop_label.text()
    assert offending(texts) == []
