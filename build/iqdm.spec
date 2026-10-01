# PyInstaller spec for IQ Data Manager: onedir, windowed.
#
# Build from the repository root into output folders that do not exist yet:
#
#   PYINSTALLER_CONFIG_DIR=build/pyinstaller-cache \
#     pyinstaller build/iqdm.spec --distpath dist/<name> --workpath build/work-<name>
#
# Do not pass --noconfirm or --clean. Both delete existing build output.
# PYINSTALLER_CONFIG_DIR keeps PyInstaller's cache inside the repository.
#
# Check the result with:  dist/<name>/IQDataManager/IQDataManager.exe --smoke-test
# A windowed build has no console. Exit code 0 means the window and schema loaded.

from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

a = Analysis(
    [str(SRC / "iqdm" / "__main__.py")],
    pathex=[str(SRC)],
    datas=[(str(SRC / "iqdm" / "db" / "schema.sql"), "iqdm/db")],
    hiddenimports=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="IQDataManager",
    console=False,
    debug=False,
    strip=False,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="IQDataManager",
    strip=False,
    upx=False,
)
