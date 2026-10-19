"""The drop-down list with a tick box per entry (DECISIONS.md D78)."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from iqdm.gui.widgets.check_combo import CheckComboBox


@pytest.fixture
def combo(qtbot) -> CheckComboBox:
    box = CheckComboBox("All sites")
    qtbot.addWidget(box)
    box.set_items([("SiteA", 1), ("SiteB", 2), ("SiteC", 3)])
    return box


def click_entry(qtbot, combo: CheckComboBox, row: int) -> None:
    view = combo.view()
    rect = view.visualRect(combo.model().index(row, 0))
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())


def test_nothing_ticked_shows_the_all_text(combo):
    assert combo.items() == ["SiteA", "SiteB", "SiteC"]
    assert combo.checked_data() == []
    assert combo.summary() == "All sites"
    assert combo.toolTip() == ""


def test_ticked_entries_are_named_in_list_order(combo):
    combo.set_checked([3, 1])
    assert combo.checked_data() == [1, 3]
    assert combo.checked_texts() == ["SiteA", "SiteC"]
    assert combo.summary() == "SiteA, SiteC"
    assert combo.toolTip() == "SiteA\nSiteC"
    combo.clear_checks()
    assert combo.summary() == "All sites"


def test_a_click_ticks_an_entry_and_leaves_the_list_open(qtbot, combo):
    changes = []
    combo.changed.connect(lambda: changes.append(combo.checked_data()))
    combo.showPopup()
    qtbot.waitUntil(lambda: combo.view().isVisible())
    click_entry(qtbot, combo, 1)
    assert combo.checked_data() == [2]
    assert combo.view().isVisible()
    click_entry(qtbot, combo, 2)
    click_entry(qtbot, combo, 1)  # a second click unticks
    assert combo.checked_data() == [3]
    assert changes == [[2], [2, 3], [3]]
    combo.hidePopup()


def test_the_space_key_ticks_the_current_entry(qtbot, combo):
    combo.showPopup()
    qtbot.waitUntil(lambda: combo.view().isVisible())
    combo.view().setCurrentIndex(combo.model().index(0, 0))
    QTest.keyClick(combo.view(), Qt.Key.Key_Space)
    assert combo.checked_data() == [1]
    combo.hidePopup()


def test_new_entries_keep_the_ticks_on_the_same_data(combo):
    combo.set_checked([2, 3])
    changes = []
    combo.changed.connect(lambda: changes.append(True))
    combo.set_items([("SiteB", 2), ("SiteC", 3), ("SiteD", 4)])
    assert combo.checked_data() == [2, 3]
    assert changes == []  # the ticks did not change
    combo.set_items([("SiteB", 2), ("SiteD", 4)])  # SiteC left the database
    assert combo.checked_data() == [2]
    assert changes == [True]
