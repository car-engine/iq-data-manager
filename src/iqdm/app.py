"""Application entry point: the QApplication and the main window with three tabs."""

import argparse
import sys
from importlib import resources

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget

from iqdm import __version__
from iqdm.gui.log_tab import LogTab
from iqdm.gui.transfer_tab import TransferTab
from iqdm.gui.viewer_tab import ViewerTab

APP_NAME = "IQ Data Manager"


class MainWindow(QMainWindow):
    """Top-level window holding the Viewer, Log recording and Move / copy tabs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1280, 800)

        self.viewer_tab = ViewerTab()
        self.log_tab = LogTab()
        self.transfer_tab = TransferTab()

        self.tabs = QTabWidget()
        self.tabs.addTab(self.viewer_tab, "Viewer")
        self.tabs.addTab(self.log_tab, "Log recording")
        self.tabs.addTab(self.transfer_tab, "Move / copy")
        self.setCentralWidget(self.tabs)

        self.statusBar().showMessage(f"Version {__version__}")


def read_schema_text() -> str:
    """Return the bundled schema.sql. Fails if the package data is missing."""
    return resources.files("iqdm.db").joinpath("schema.sql").read_text(encoding="utf-8")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="iqdm", description=APP_NAME)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="build the main window, quit at once and exit with 0 on success",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def _smoke_test(app: QApplication) -> int:
    """Check the bundled schema and the main window, then quit. Returns an exit code.

    A windowed PyInstaller build has no console, so the exit code is the result.
    """
    try:
        if "CREATE TABLE recordings" not in read_schema_text():
            print("smoke test: schema.sql has no recordings table", file=sys.stderr)
            return 1
        window = MainWindow()
        window.show()
        QTimer.singleShot(0, app.quit)
        app.exec()
        tab_count = window.tabs.count()
        window.close()
    except Exception as exc:
        print(f"smoke test failed: {exc!r}", file=sys.stderr)
        return 1
    if tab_count != 3:
        print(f"smoke test: expected 3 tabs, found {tab_count}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Start the GUI. Returns the process exit code."""
    args = _parse_args(argv)
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)

    if args.smoke_test:
        return _smoke_test(app)

    window = MainWindow()
    window.show()
    return app.exec()
