# PyInstaller spec for IQ Data Manager: onedir, two programs in one folder.
#
#   IQDataManager.exe        the windowed app
#   IQDataManager-check.exe  a console program for the diagnostics of the NAS field
#                            test: copy-check, db-check, make-test-set (DECISIONS.md D57)
#
# Build from the repository root into output folders that do not exist yet:
#
#   PYINSTALLER_CONFIG_DIR=build/pyinstaller-cache \
#     pyinstaller build/iqdm.spec --distpath dist/<name> --workpath build/work-<name>
#
# Do not pass --noconfirm or --clean. Both delete existing build output.
# PYINSTALLER_CONFIG_DIR keeps PyInstaller's cache inside the repository.
#
# Check the result with:
#   dist/<name>/IQDataManager/IQDataManager.exe --smoke-test
#   dist/<name>/IQDataManager/IQDataManager-check.exe --help
# A windowed build has no console. Exit code 0 means the window and schema loaded.

from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

app = Analysis(
    [str(SRC / "iqdm" / "__main__.py")],
    pathex=[str(SRC)],
    datas=[(str(SRC / "iqdm" / "db" / "schema.sql"), "iqdm/db")],
    hiddenimports=[],
    excludes=["tkinter"],
    noarchive=False,
)

check = Analysis(
    [str(SRC / "iqdm" / "check_main.py")],
    pathex=[str(SRC)],
    datas=[(str(SRC / "iqdm" / "db" / "schema.sql"), "iqdm/db")],
    hiddenimports=[],
    excludes=["tkinter", "PySide6", "shiboken6"],  # the diagnostics have no GUI
    noarchive=False,
)

app_exe = EXE(
    PYZ(app.pure),
    app.scripts,
    [],
    exclude_binaries=True,
    name="IQDataManager",
    console=False,
    debug=False,
    strip=False,
    upx=False,
)

check_exe = EXE(
    PYZ(check.pure),
    check.scripts,
    [],
    exclude_binaries=True,
    name="IQDataManager-check",
    console=True,
    debug=False,
    strip=False,
    upx=False,
)

coll = COLLECT(
    app_exe,
    app.binaries,
    app.datas,
    check_exe,
    check.binaries,
    check.datas,
    name="IQDataManager",
    strip=False,
    upx=False,
)
