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

from iqdm.config import Config
from iqdm.db import repository as repo
from iqdm.db.connection import write_transaction
from iqdm.gui.log_tab import LogTab
from iqdm.gui.settings_tab import SettingsTab
from iqdm.gui.viewer_tab import ViewerTab
from iqdm.models import (
    IN_PLACE_NOTE,
    ArchiveState,
    Channel,
    Operation,
    Param,
    Recording,
    TransferEntry,
)
from make_fixtures import ChannelSpec

FORBIDDEN = re.compile(
    r"DECISIONS|\bSPEC\b|\bD\d{1,2}\b|\bO\d{1,2}\b|\bMilestone\b"
    r"|db_path|nas_roots|display_utc_offset_hours|coverage_highlight_percent|user_version"
    r"|schema|journal|busy timeout|foreign keys",
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


def test_log_tab_text_is_plain(qtbot, db_path):
    tab = LogTab(Config(db_path=str(db_path)))
    qtbot.addWidget(tab)
    qtbot.waitUntil(lambda: not tab.runner.busy, timeout=10_000)
    texts = visible_texts(tab) + [item.text for item in tab.checklist.items]
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
