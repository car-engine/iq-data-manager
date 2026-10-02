"""User-facing text holds no planning references or internals (CLAUDE.md, D38).

Walks the visible text of each tab: labels, buttons, group titles, placeholders,
table headings and tooltips. Decision numbers, SPEC sections, open items, config key
names and database internals belong in code comments and docs.
"""

import re

import pytest
from PySide6.QtWidgets import (
    QAbstractButton,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTableWidget,
    QWidget,
)

from iqdm.config import Config
from iqdm.gui.log_tab import LogTab
from iqdm.gui.settings_tab import SettingsTab

FORBIDDEN = re.compile(
    r"DECISIONS|\bSPEC\b|\bD\d{1,2}\b|\bO\d{1,2}\b|\bMilestone\b"
    r"|db_path|nas_roots|display_utc_offset_hours|user_version"
    r"|schema|journal|busy timeout|foreign keys",
    re.IGNORECASE,
)


def visible_texts(root: QWidget, skip_tooltips: tuple[QWidget, ...] = ()) -> list[str]:
    texts: list[str] = []
    for widget in [root, *root.findChildren(QWidget)]:
        if isinstance(widget, QLabel | QAbstractButton):
            texts.append(widget.text())
        if isinstance(widget, QGroupBox):
            texts.append(widget.title())
        if isinstance(widget, QLineEdit):
            texts.append(widget.placeholderText())
        if isinstance(widget, QTableWidget):
            for col in range(widget.columnCount()):
                item = widget.horizontalHeaderItem(col)
                if item is not None:
                    texts.append(item.text())
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
