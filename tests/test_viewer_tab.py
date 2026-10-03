"""GUI tests for the Viewer tab (pytest-qt, offscreen). Databases and folders in tmp_path.

Database reads and gap scans run on a thread pool. Each test waits for the tab's
TaskRunner to be idle before it checks what the tab shows.
"""

import sqlite3
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

from iqdm.config import Config
from iqdm.db import repository as repo
from iqdm.db.connection import write_transaction
from iqdm.entry import ItemState
from iqdm.gui.log_tab import NO_DATABASE
from iqdm.gui.viewer_tab import FOLDER_NOT_OPENED, ViewerTab
from iqdm.gui.widgets.checklist import DARK_COLOURS, LIGHT_COLOURS, MARKS
from iqdm.gui.widgets.recording_model import (
    COL_COVERAGE,
    COL_ID,
    COL_SIZE,
    COL_START,
    COL_STATE,
    ID_ROLE,
)
from iqdm.models import (
    IN_PLACE_NOTE,
    ArchiveState,
    Channel,
    Operation,
    Param,
    Recording,
    TransferEntry,
    Verification,
)
from iqdm.viewer import NEWER_DATABASE
from make_fixtures import ChannelSpec

T0 = 1790733600.0  # 2026-09-30T02:00:00Z, 10:00 at UTC+8
DAY = 86400.0
INFO = MARKS[ItemState.INFO]


def wait_idle(qtbot, tab: ViewerTab) -> None:
    qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)


def channels_from(info) -> list[Channel]:
    return [
        Channel(
            channel_index=c.index,
            sub_path=c.sub_path,
            band="VHF",
            fc_hz=145.8e6,
            fs_hz=info.fs_hz,
            start_unix=c.start_unix,
            end_unix=c.end_unix,
            n_files=c.n_files,
            total_bytes=c.total_bytes,
        )
        for c in info.channels
    ]


@pytest.fixture
def catalogue(db_path, make_recording) -> dict[str, int]:
    """Three recordings. "gappy" has a real folder with gaps in channel 1 (85% coverage).

    "full" is archived in place on the NAS (not verified). "legacy" has no file counts.
    Returns their ids by name; the database is db_path.
    """
    info = make_recording(
        n_channels=2, n_slots=20, channels={1: ChannelSpec(gaps=frozenset({3, 4, 10}))}
    )
    root = Path(info.root)

    def fill(conn) -> dict[str, int]:
        site_a = repo.add_site(conn, "SiteA").id
        site_b = repo.add_site(conn, "SiteB").id
        gappy = repo.insert_recording(
            conn,
            Recording(
                logged_by="userA",
                site_id=site_a,
                storage_root=str(root.parent),
                rel_path=root.name,
                channels=channels_from(info),
                params=[
                    Param(param="SDR", value="USRP X310"),
                    Param(param="LNA gain", value="10", unit="dB"),
                    Param(param="Antenna", value="Monopole B", channel_index=1),
                    Param(param="LNA gain", value="20", unit="dB", channel_index=1),
                ],
                recording_plan_ref="plan-7",
                remarks="Same frequency on two antennas",
            ),
        )
        full = repo.insert_recording(
            conn,
            Recording(
                logged_by="userB",
                site_id=site_b,
                storage_root=r"\\nas\recordings",
                rel_path="full",
                channels=[
                    Channel(
                        channel_index=0,
                        band="UHF",
                        fc_hz=433.92e6,
                        fs_hz=1000.0,
                        start_unix=T0 + DAY,
                        end_unix=T0 + DAY + 100,
                        n_files=100,
                        total_bytes=400_000,
                    )
                ],
                archive_state=ArchiveState.ARCHIVED,
                archived_at="2026-10-01T05:00:00Z",
            ),
        )
        repo.insert_transfer(
            conn,
            TransferEntry(
                recording_id=full,
                operation=Operation.CHECK,
                source=r"\\nas\recordings\full",
                started_at="2026-10-01T05:00:00Z",
                finished_at="2026-10-01T05:00:00Z",
                performed_by="userB",
                verification=Verification.SKIPPED,
                notes=IN_PLACE_NOTE,
            ),
        )
        legacy = repo.insert_recording(
            conn,
            Recording(
                logged_by="legacy-import",
                site_id=site_a,
                storage_root=str(root.parent),
                rel_path="missing-folder",
                channels=[
                    Channel(
                        channel_index=0,
                        fc_hz=868.3e6,
                        fs_hz=1000.0,
                        start_unix=T0 - DAY,
                        end_unix=T0 - DAY + 60,
                    )
                ],
            ),
        )
        return {"gappy": gappy, "full": full, "legacy": legacy}

    return write_transaction(db_path, fill)


@pytest.fixture
def make_tab(qtbot):
    tabs: list[ViewerTab] = []

    def _make(config: Config, **kw) -> ViewerTab:
        tab = ViewerTab(config, **kw)
        qtbot.addWidget(tab)
        tabs.append(tab)
        wait_idle(qtbot, tab)
        return tab

    yield _make
    for tab in tabs:
        tab.runner.wait(10_000)


@pytest.fixture
def tab(make_tab, db_path, catalogue) -> ViewerTab:
    return make_tab(Config(db_path=str(db_path)))


def shown_ids(tab: ViewerTab) -> list[int]:
    return [tab.model.index(r, 0).data(ID_ROLE) for r in range(tab.model.rowCount())]


def cell(tab: ViewerTab, recording_id: int, col: int, role=Qt.ItemDataRole.DisplayRole):
    for r in range(tab.model.rowCount()):
        if tab.model.index(r, 0).data(ID_ROLE) == recording_id:
            return tab.model.index(r, col).data(role)
    raise AssertionError(f"recording {recording_id} not shown")


def select(qtbot, tab: ViewerTab, recording_id: int) -> None:
    for r in range(tab.model.rowCount()):
        if tab.model.index(r, 0).data(ID_ROLE) == recording_id:
            tab.table.selectRow(r)
            break
    wait_idle(qtbot, tab)
    assert tab.details is not None
    assert tab.details.recording.id == recording_id


def select_channel(tab: ViewerTab, row: int) -> None:
    tab.channel_table.selectRow(row)


def header(tab: ViewerTab, col: int) -> str:
    return tab.model.headerData(col, Qt.Orientation.Horizontal)


def set_user_version(path: Path, value: int) -> None:
    raw = sqlite3.connect(path, autocommit=True)
    raw.execute(f"PRAGMA user_version = {value}")
    raw.close()


# ---------------------------------------------------------------------------
# Loading and the list
# ---------------------------------------------------------------------------


def test_without_a_database_the_tab_says_where_to_set_it(make_tab):
    tab = make_tab(Config())
    assert tab.message == (ItemState.TODO, NO_DATABASE, "")
    assert tab.message_label.text().endswith(NO_DATABASE)
    assert tab.model.rowCount() == 0
    for button in (tab.refresh_button, tab.open_button, tab.edit_button, tab.scan_button):
        assert not button.isEnabled()


def test_list_shows_every_recording_newest_first(tab, catalogue):
    assert shown_ids(tab) == [catalogue["full"], catalogue["gappy"], catalogue["legacy"]]
    assert tab.message is None
    assert tab.count_label.text().startswith("3 shown \N{MIDDLE DOT} refreshed ")
    assert tab.count_label.text().endswith("(UTC+8)")
    assert header(tab, COL_START) == "Start (UTC+8)"


def test_cells_show_plain_text(tab, catalogue):
    gappy = catalogue["gappy"]
    texts = [cell(tab, gappy, c) for c in range(10)]
    assert texts == [
        str(gappy),
        "2026-09-30 10:00",
        "SiteA",
        "2",
        "145.8 \N{MULTIPLICATION SIGN} 2",
        "20 s",
        f"{INFO} 85.0%",
        "148.0 kB",  # 37 files of 4,000 bytes
        "local",
        "userA",
    ]
    legacy = catalogue["legacy"]
    assert cell(tab, legacy, COL_COVERAGE) == "unknown"
    assert cell(tab, legacy, COL_SIZE) == "unknown"
    assert "not in the database" in cell(tab, legacy, COL_SIZE, Qt.ItemDataRole.ToolTipRole)


def test_columns_sort_as_numbers(tab, catalogue):
    tab.table.sortByColumn(COL_SIZE, Qt.SortOrder.AscendingOrder)
    assert shown_ids(tab) == [catalogue["legacy"], catalogue["gappy"], catalogue["full"]]
    tab.table.sortByColumn(COL_COVERAGE, Qt.SortOrder.DescendingOrder)
    assert shown_ids(tab) == [catalogue["full"], catalogue["gappy"], catalogue["legacy"]]
    tab.table.sortByColumn(COL_ID, Qt.SortOrder.AscendingOrder)
    assert shown_ids(tab) == sorted(catalogue.values())


def test_sorting_keeps_the_selected_recording(qtbot, tab, catalogue):
    select(qtbot, tab, catalogue["legacy"])
    tab.table.sortByColumn(COL_SIZE, Qt.SortOrder.AscendingOrder)
    rows = tab.table.selectionModel().selectedRows()
    assert [r.data(ID_ROLE) for r in rows] == [catalogue["legacy"]]
    assert rows[0].row() == 0
    assert tab.selected_id == catalogue["legacy"]


def test_a_refresh_keeps_the_sort_order(qtbot, tab, catalogue):
    tab.table.sortByColumn(COL_ID, Qt.SortOrder.AscendingOrder)
    tab.refresh_button.click()
    wait_idle(qtbot, tab)
    assert shown_ids(tab) == sorted(catalogue.values())


def test_sort_by_id_is_numeric_beyond_nine(make_tab, db_path):
    def fill(conn):
        site = repo.add_site(conn, "S").id
        for i in range(12):
            ch = Channel(
                channel_index=0, fc_hz=1e6, fs_hz=1e3, start_unix=T0 + i, end_unix=T0 + i + 1
            )
            repo.insert_recording(
                conn,
                Recording(
                    logged_by="u",
                    site_id=site,
                    storage_root="C:/x",
                    rel_path=f"r{i}",
                    channels=[ch],
                ),
            )

    write_transaction(db_path, fill)
    tab = make_tab(Config(db_path=str(db_path)))
    tab.table.sortByColumn(COL_ID, Qt.SortOrder.AscendingOrder)
    assert shown_ids(tab) == list(range(1, 13))


def test_not_verified_state_is_amber_with_words(tab, catalogue):
    full = catalogue["full"]
    assert cell(tab, full, COL_STATE) == "archived, not verified"
    assert (
        cell(tab, full, COL_STATE, Qt.ItemDataRole.ForegroundRole) == LIGHT_COLOURS[ItemState.INFO]
    )
    assert "never compared" in cell(tab, full, COL_STATE, Qt.ItemDataRole.ToolTipRole)
    assert cell(tab, catalogue["gappy"], COL_STATE, Qt.ItemDataRole.ForegroundRole) is None


def dark_palette() -> QPalette:
    pal = QPalette()
    for role in (QPalette.ColorRole.Base, QPalette.ColorRole.Window):
        pal.setColor(role, QColor(45, 45, 45))
    pal.setColor(QPalette.ColorRole.Text, QColor(230, 230, 230))
    return pal


def test_low_coverage_is_amber_with_a_mark_in_both_themes(qtbot, tab, catalogue):
    gappy = catalogue["gappy"]
    assert (
        cell(tab, gappy, COL_COVERAGE, Qt.ItemDataRole.ForegroundRole)
        == LIGHT_COLOURS[ItemState.INFO]
    )
    assert "Below 99%" in cell(tab, gappy, COL_COVERAGE, Qt.ItemDataRole.ToolTipRole)
    assert cell(tab, catalogue["full"], COL_COVERAGE, Qt.ItemDataRole.ForegroundRole) is None
    tab.setPalette(dark_palette())
    assert (
        cell(tab, gappy, COL_COVERAGE, Qt.ItemDataRole.ForegroundRole)
        == DARK_COLOURS[ItemState.INFO]
    )
    select(qtbot, tab, gappy)
    coverage_item = tab.channel_table.item(1, 7)
    assert coverage_item.text() == f"{INFO} 85.0%"
    assert coverage_item.foreground().color() == DARK_COLOURS[ItemState.INFO]
    assert tab.channel_table.item(0, 7).text() == "100.0%"


def test_a_new_threshold_changes_the_marks(qtbot, tab, db_path, catalogue):
    tab.apply_config(Config(db_path=str(db_path), coverage_highlight_percent=80.0))
    gappy = catalogue["gappy"]
    assert cell(tab, gappy, COL_COVERAGE) == "85.0%"
    assert cell(tab, gappy, COL_COVERAGE, Qt.ItemDataRole.ForegroundRole) is None
    tab.apply_config(Config(db_path=str(db_path), coverage_highlight_percent=100.0))
    assert cell(tab, gappy, COL_COVERAGE) == f"{INFO} 85.0%"


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def test_filter_lists_come_from_the_database(tab):
    sites = [tab.site_combo.itemText(i) for i in range(tab.site_combo.count())]
    bands = [tab.band_combo.itemText(i) for i in range(tab.band_combo.count())]
    assert sites == ["All sites", "SiteA", "SiteB"]
    assert bands == ["All bands", "UHF", "VHF"]
    assert tab.start_from_label.text() == "Start date from (UTC+8)"


def apply(qtbot, tab: ViewerTab) -> None:
    tab.apply_button.click()
    wait_idle(qtbot, tab)


def test_band_filter_and_clear(qtbot, tab, catalogue):
    tab.band_combo.setCurrentIndex(tab.band_combo.findData("UHF"))
    apply(qtbot, tab)
    assert shown_ids(tab) == [catalogue["full"]]
    assert tab.count_label.text().startswith("1 shown")
    tab.clear_button.click()
    wait_idle(qtbot, tab)
    assert len(shown_ids(tab)) == 3
    assert tab.band_combo.currentIndex() == 0
    assert tab.active_filter is None


def test_site_and_state_filters(qtbot, tab, catalogue):
    tab.site_combo.setCurrentIndex(tab.site_combo.findText("SiteA"))
    tab.state_combo.setCurrentIndex(tab.state_combo.findData(ArchiveState.LOCAL))
    apply(qtbot, tab)
    assert shown_ids(tab) == [catalogue["gappy"], catalogue["legacy"]]


def test_text_and_frequency_filters(qtbot, tab, catalogue):
    tab.rf_edit.setText("monopole")
    apply(qtbot, tab)
    assert shown_ids(tab) == [catalogue["gappy"]]
    tab.rf_edit.clear()
    tab.fc_min_edit.setText("400")
    tab.fc_max_edit.setText("500")
    apply(qtbot, tab)
    assert shown_ids(tab) == [catalogue["full"]]


def test_date_filter_uses_the_display_offset(qtbot, tab, catalogue):
    tab.start_from_edit.setText("2026-09-30")
    tab.start_to_edit.setText("2026-09-30")
    apply(qtbot, tab)
    assert shown_ids(tab) == [catalogue["gappy"]]  # 10:00 at UTC+8


def test_enter_in_a_field_applies(qtbot, tab, catalogue):
    tab.remarks_edit.setText("antennas")
    tab.remarks_edit.returnPressed.emit()
    wait_idle(qtbot, tab)
    assert shown_ids(tab) == [catalogue["gappy"]]


def test_a_wrong_filter_value_is_marked_and_nothing_is_queried(qtbot, tab):
    tab.start_from_edit.setText("30.09.2026")
    tab.fc_min_edit.setText("abc")
    tab.apply_button.click()
    assert not tab.runner.busy
    assert tab.filter_error.isVisibleTo(tab)
    assert tab.filter_error.text().count(MARKS[ItemState.ERROR]) == 2
    assert "YYYY-MM-DD" in tab.filter_error.text()
    assert len(shown_ids(tab)) == 3
    tab.clear_button.click()
    wait_idle(qtbot, tab)
    assert not tab.filter_error.isVisibleTo(tab)


def test_a_late_list_is_dropped(qtbot, tab, catalogue):
    tab.band_combo.setCurrentIndex(tab.band_combo.findData("UHF"))
    tab.apply_button.click()
    tab.clear_button.click()  # replaces the filtered load before it returns
    wait_idle(qtbot, tab)
    assert len(shown_ids(tab)) == 3


# ---------------------------------------------------------------------------
# Selection and details
# ---------------------------------------------------------------------------


def test_buttons_need_a_selection(qtbot, tab, catalogue):
    assert tab.refresh_button.isEnabled()
    assert not tab.open_button.isEnabled()
    assert not tab.edit_button.isEnabled()
    assert not tab.scan_button.isEnabled()
    select(qtbot, tab, catalogue["gappy"])
    assert tab.open_button.isEnabled()
    assert tab.edit_button.isEnabled()
    assert tab.scan_button.isEnabled()


def test_selecting_a_recording_shows_channels_and_details(qtbot, tab, catalogue):
    select(qtbot, tab, catalogue["gappy"])
    assert tab.channel_table.rowCount() == 2
    assert tab.channel_table.item(1, 4).text() == "2026-09-30 10:00:00"
    assert tab.channel_table.item(1, 3).text() == "1 kHz"
    assert tab.channel_table.item(1, 6).text() == "17"
    assert tab.channels_box.title() == f"Channels \N{MIDDLE DOT} recording {catalogue['gappy']}"
    assert tab.details_title.text() == f"Recording {catalogue['gappy']} \N{MIDDLE DOT} SiteA"
    params = [
        [tab.param_table.item(r, c).text() for c in range(4)]
        for r in range(tab.param_table.rowCount())
    ]
    assert params == [["Recording", "SDR", "USRP X310", ""], ["Recording", "LNA gain", "10 dB", ""]]
    assert tab.plan_label.text() == "plan-7"
    assert tab.remarks_label.text() == "Same frequency on two antennas"
    assert tab.logged_label.text().startswith("by userA on ")
    assert tab.transfer_hint.text() == "No transfers yet."
    assert not tab.not_verified_label.isVisibleTo(tab)


def set_times(db_path: Path, recording_id: int, created: str, updated: str) -> None:
    raw = sqlite3.connect(db_path, autocommit=True)
    raw.execute(
        "UPDATE recordings SET created_at = ?, updated_at = ? WHERE id = ?",
        (created, updated, recording_id),
    )
    raw.close()


def test_details_name_the_last_change(qtbot, tab, db_path, catalogue):
    gappy = catalogue["gappy"]
    set_times(db_path, gappy, "2026-10-01T00:00:00Z", "2026-10-02T03:30:00Z")
    tab.refresh_button.click()
    wait_idle(qtbot, tab)
    select(qtbot, tab, gappy)
    assert tab.logged_label.text() == (
        "by userA on 2026-10-01 08:00; last changed on 2026-10-02 11:30"
    )


def test_details_leave_out_the_last_change_when_there_was_none(qtbot, tab, db_path, catalogue):
    gappy = catalogue["gappy"]
    set_times(db_path, gappy, "2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z")
    tab.refresh_button.click()
    wait_idle(qtbot, tab)
    select(qtbot, tab, gappy)
    assert tab.logged_label.text() == "by userA on 2026-10-01 08:00"


def test_selecting_a_channel_shows_its_rf_chain_and_path(qtbot, tab, catalogue):
    select(qtbot, tab, catalogue["gappy"])
    select_channel(tab, 1)
    assert tab.details_title.text().endswith("channel 1 \N{MIDDLE DOT} 145.8 MHz")
    params = [
        [tab.param_table.item(r, c).text() for c in range(4)]
        for r in range(tab.param_table.rowCount())
    ]
    assert params == [
        ["Recording", "SDR", "USRP X310", ""],
        ["Ch 1", "Antenna", "Monopole B", ""],
        ["Ch 1", "LNA gain", "20 dB", "replaces the Recording value 10 dB"],
    ]
    assert tab.path_label.text().endswith("\\1")


def test_archived_in_place_shows_history_and_the_not_verified_note(qtbot, tab, catalogue):
    select(qtbot, tab, catalogue["full"])
    assert tab.not_verified_label.isVisibleTo(tab)
    assert tab.not_verified_label.text().startswith(f"{INFO}  Not verified.")
    assert tab.transfer_table.rowCount() == 1
    row = [tab.transfer_table.item(0, c).text() for c in range(5)]
    assert row == ["2026-10-01 13:00", "Check", "whole recording", "not verified", "userB"]
    assert tab.transfer_table.item(0, 0).toolTip() == IN_PLACE_NOTE
    assert "archived on 2026-10-01 13:00" in tab.logged_label.text()
    assert tab.path_label.text() == r"\\nas\recordings\full"


def test_refresh_keeps_the_selection(qtbot, tab, db_path, catalogue):
    select(qtbot, tab, catalogue["gappy"])

    def add(conn):
        site = repo.find_site(conn, "SiteA").id
        ch = Channel(
            channel_index=0,
            fc_hz=1e6,
            fs_hz=1e3,
            start_unix=T0 + 5 * DAY,
            end_unix=T0 + 5 * DAY + 1,
        )
        return repo.insert_recording(
            conn,
            Recording(
                logged_by="u", site_id=site, storage_root="C:/x", rel_path="new", channels=[ch]
            ),
        )

    new_id = write_transaction(db_path, add)
    tab.refresh_button.click()
    wait_idle(qtbot, tab)
    assert shown_ids(tab)[0] == new_id
    assert tab.selected_id == catalogue["gappy"]
    assert tab.table.selectionModel().selectedRows()[0].data(ID_ROLE) == catalogue["gappy"]
    assert tab.channel_table.rowCount() == 2


def test_a_filter_that_hides_the_selection_clears_the_details(qtbot, tab, catalogue):
    select(qtbot, tab, catalogue["gappy"])
    tab.band_combo.setCurrentIndex(tab.band_combo.findData("UHF"))
    apply(qtbot, tab)
    assert tab.details is None
    assert tab.channel_table.rowCount() == 0
    assert not tab.edit_button.isEnabled()


# ---------------------------------------------------------------------------
# Gap scan
# ---------------------------------------------------------------------------


def test_scan_shows_the_timeline_and_gaps(qtbot, tab, catalogue):
    select(qtbot, tab, catalogue["gappy"])
    assert "Scan the recording folder" in tab.scan_status.text()
    assert not tab.timeline.isVisibleTo(tab)
    tab.scan_button.click()
    wait_idle(qtbot, tab)
    assert tab.scan is not None
    assert tab.scan_status.text() == f"{MARKS[ItemState.OK]}  Scanned 37 files."
    assert tab.timeline.isVisibleTo(tab)
    assert [r.label for r in tab.timeline.rows] == ["Ch 0", "Ch 1"]
    assert tab.gap_label.text().splitlines() == [
        "Times in UTC+8.",
        "Ch 0: no gaps.",
        "Ch 1: 3 missing seconds in 2 gaps: 2026-09-30 10:00:03 (2 s), 2026-09-30 10:00:10 (1 s).",
    ]
    assert not tab.difference_label.isVisibleTo(tab)


def test_scan_reports_differences_from_the_database(qtbot, tab, catalogue, db_path):
    select(qtbot, tab, catalogue["gappy"])
    folder = Path(tab.path_label.text())
    (folder / "0" / f"{int(T0) + 30}.dat").write_bytes(b"\0" * 4000)
    tab.scan_button.click()
    wait_idle(qtbot, tab)
    assert tab.difference_label.isVisibleTo(tab)
    assert (
        tab.difference_label.text()
        == f"{INFO} Channel 0: the folder holds 21 files, the database lists 20."
    )


def test_scan_of_a_missing_folder_is_an_error(qtbot, tab, catalogue):
    select(qtbot, tab, catalogue["legacy"])
    tab.scan_button.click()
    wait_idle(qtbot, tab)
    assert tab.scan_status.text().startswith(
        f"{MARKS[ItemState.ERROR]}  Cannot scan the folder: folder not found"
    )
    assert not tab.timeline.isVisibleTo(tab)


def test_cancel_drops_the_scan(qtbot, tab, catalogue):
    select(qtbot, tab, catalogue["gappy"])
    tab.scan_button.click()
    assert tab.cancel_scan_button.isEnabled()
    assert not tab.scan_button.isEnabled()
    tab.cancel_scan_button.click()
    wait_idle(qtbot, tab)
    assert tab.scan is None
    assert tab.scan_status.text().endswith("Scan cancelled.")
    assert tab.scan_button.isEnabled()


def test_selecting_another_recording_drops_the_scan(qtbot, tab, catalogue):
    select(qtbot, tab, catalogue["gappy"])
    tab.scan_button.click()
    wait_idle(qtbot, tab)
    select(qtbot, tab, catalogue["full"])
    assert tab.scan is None
    assert not tab.timeline.isVisibleTo(tab)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_a_new_offset_redraws_times(qtbot, tab, db_path, catalogue):
    select(qtbot, tab, catalogue["gappy"])
    tab.scan_button.click()
    wait_idle(qtbot, tab)
    tab.apply_config(Config(db_path=str(db_path), display_utc_offset_hours=0.0))
    assert header(tab, COL_START) == "Start (UTC)"
    assert cell(tab, catalogue["gappy"], COL_START) == "2026-09-30 02:00"
    assert tab.start_from_label.text() == "Start date from (UTC)"
    assert tab.channel_table.horizontalHeaderItem(4).text() == "Start (UTC)"
    assert tab.channel_table.item(0, 4).text() == "2026-09-30 02:00:00"
    assert tab.gap_label.text().splitlines()[0] == "Times in UTC."
    assert tab.selected_id == catalogue["gappy"]


def test_a_new_database_reloads(qtbot, tab, tmp_path, catalogue):
    from iqdm.db.connection import create_database

    other = tmp_path / "other.db"
    create_database(other)
    select(qtbot, tab, catalogue["gappy"])
    tab.apply_config(Config(db_path=str(other)))
    wait_idle(qtbot, tab)
    assert shown_ids(tab) == []
    assert tab.details is None
    assert [tab.site_combo.itemText(i) for i in range(tab.site_combo.count())] == ["All sites"]


def test_removing_the_database_path(qtbot, tab):
    tab.apply_config(Config())
    wait_idle(qtbot, tab)
    assert shown_ids(tab) == []
    assert tab.message[1] == NO_DATABASE


def test_a_newer_database_is_shown_with_an_amber_line(make_tab, db_path, catalogue):
    set_user_version(db_path, 99)
    tab = make_tab(Config(db_path=str(db_path)))
    assert len(shown_ids(tab)) == 3
    assert tab.message == (ItemState.INFO, NEWER_DATABASE, "")


def test_a_file_that_is_not_an_app_database_is_red(make_tab, db_path, catalogue):
    set_user_version(db_path, 0)
    tab = make_tab(Config(db_path=str(db_path)))
    assert shown_ids(tab) == []
    state, text, tooltip = tab.message
    assert state is ItemState.ERROR
    assert text.startswith("This file is not an IQ Data Manager database.")
    assert tooltip  # the technical text
    assert tab.message_label.text().startswith(MARKS[ItemState.ERROR])


def test_an_older_database_is_red(make_tab, db_path, catalogue, monkeypatch):
    monkeypatch.setattr("iqdm.db.version.LATEST_VERSION", 2)
    tab = make_tab(Config(db_path=str(db_path)))
    assert tab.message[0] is ItemState.ERROR
    assert "older version" in tab.message[1]


def test_a_missing_database_file_is_red(make_tab, tmp_path):
    tab = make_tab(Config(db_path=str(tmp_path / "absent.db")))
    assert tab.message[0] is ItemState.ERROR
    assert tab.message[1].startswith("Database file not found.")


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def test_open_folder_opens_the_recording_or_channel_folder(qtbot, make_tab, db_path, catalogue):
    opened: list[Path] = []
    tab = make_tab(Config(db_path=str(db_path)), open_folder=lambda p: opened.append(p) or True)
    select(qtbot, tab, catalogue["full"])
    tab.open_button.click()
    assert opened == [Path(r"\\nas\recordings\full")]
    select(qtbot, tab, catalogue["gappy"])
    select_channel(tab, 1)
    tab.open_button.click()
    assert opened[-1].name == "1"
    assert tab.message is None


def test_a_folder_that_cannot_be_opened_is_reported(qtbot, make_tab, db_path, catalogue):
    tab = make_tab(Config(db_path=str(db_path)), open_folder=lambda p: False)
    select(qtbot, tab, catalogue["full"])
    tab.open_button.click()
    assert tab.message == (ItemState.ERROR, FOLDER_NOT_OPENED, r"\\nas\recordings\full")


def test_edit_entry_asks_for_the_log_tab(qtbot, tab, catalogue):
    select(qtbot, tab, catalogue["gappy"])
    with qtbot.waitSignal(tab.edit_requested, timeout=1_000) as blocker:
        tab.edit_button.click()
    assert blocker.args == [catalogue["gappy"]]


def test_archive_copy_asks_for_the_transfer_tab(qtbot, tab, catalogue):
    """D42: the button comes with the Archive / copy tab."""
    assert not tab.transfer_button.isEnabled()  # nothing selected
    select(qtbot, tab, catalogue["gappy"])
    assert tab.transfer_button.isEnabled()
    with qtbot.waitSignal(tab.transfer_requested, timeout=1_000) as blocker:
        tab.transfer_button.click()
    assert blocker.args == [catalogue["gappy"]]
