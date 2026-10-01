"""Static checks on the package source that ruff cannot express.

These tests read the files under src/iqdm/ and parse them with ast. They write nothing.

- Only iqdm.gui and iqdm.app may import PySide6, so business logic stays portable.
- Only iqdm.db may import sqlite3, so all SQL lives in src/iqdm/db/.
- Only iqdm.transfer.delete may call .unlink() or .rmdir(). Ruff's banned-API rule
  (TID251 in pyproject.toml) covers os.remove, shutil.rmtree and similar functions.
"""

import ast
from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "iqdm"

QT_ALLOWED = ("gui/", "app.py")
SQLITE_ALLOWED = ("db/",)
DELETE_ALLOWED = ("transfer/delete.py",)
DELETE_METHODS = {"unlink", "rmdir"}


def _source_files() -> list[Path]:
    return sorted(PACKAGE_DIR.rglob("*.py"))


def _rel(path: Path) -> str:
    return path.relative_to(PACKAGE_DIR).as_posix()


def _allowed(rel: str, prefixes: tuple[str, ...]) -> bool:
    return any(rel == p or rel.startswith(p) for p in prefixes)


def module_imports(tree: ast.AST, module: str) -> list[int]:
    """Return line numbers of imports of `module` or any of its submodules."""
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        if any(n == module or n.startswith(f"{module}.") for n in names):
            lines.append(node.lineno)
    return lines


def qt_imports(tree: ast.AST) -> list[int]:
    return module_imports(tree, "PySide6")


def delete_calls(tree: ast.AST) -> list[int]:
    """Return line numbers of calls to a method named unlink or rmdir."""
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in DELETE_METHODS
    ]


def test_package_has_source_files():
    rels = [_rel(p) for p in _source_files()]
    assert "__init__.py" in rels


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        ("import PySide6", [1]),
        ("from PySide6.QtWidgets import QWidget", [1]),
        ("import PySide6.QtCore as qc", [1]),
        ("import os\nimport PySide6xyz", []),
        ("from . import widgets", []),
    ],
)
def test_qt_import_detector(snippet, expected):
    assert qt_imports(ast.parse(snippet)) == expected


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        ("p.unlink()", [1]),
        ("Path('x').unlink(missing_ok=True)", [1]),
        ("x = 1\nd.rmdir()", [2]),
        ("p.unlinked()", []),
        ("unlink = 3", []),
    ],
)
def test_delete_call_detector(snippet, expected):
    assert delete_calls(ast.parse(snippet)) == expected


def test_pyside6_imported_only_in_gui():
    offenders = []
    for path in _source_files():
        rel = _rel(path)
        if _allowed(rel, QT_ALLOWED):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders += [f"{rel}:{line}" for line in qt_imports(tree)]
    assert offenders == [], f"PySide6 imported outside gui/ and app.py: {offenders}"


def test_delete_methods_only_in_delete_module():
    offenders = []
    for path in _source_files():
        rel = _rel(path)
        if _allowed(rel, DELETE_ALLOWED):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders += [f"{rel}:{line}" for line in delete_calls(tree)]
    assert offenders == [], f"unlink/rmdir called outside transfer/delete.py: {offenders}"


def test_sqlite3_imported_only_in_db():
    offenders = []
    for path in _source_files():
        rel = _rel(path)
        if _allowed(rel, SQLITE_ALLOWED):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders += [f"{rel}:{line}" for line in module_imports(tree, "sqlite3")]
    assert offenders == [], f"sqlite3 imported outside db/: {offenders}"
