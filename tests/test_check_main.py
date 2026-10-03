"""Tests for iqdm.check_main, the console program IQDataManager-check.exe (D57).

Everything the commands write is under tmp_path.
"""

import pytest

import copy_check
import db_check
import make_fixtures
import make_nas_testset
from iqdm import __version__
from iqdm.check_main import PROG, main, usage
from iqdm.db.connection import database_status
from iqdm.db.version import SchemaStatus
from iqdm.diagnostics import copy_check as copy_check_impl
from iqdm.diagnostics import db_check as db_check_impl
from iqdm.diagnostics import fixtures, testset


def test_the_tool_scripts_are_the_package_modules():
    """tools/ keeps working, and tests that import a tool use the package code."""
    assert make_fixtures is fixtures
    assert copy_check is copy_check_impl
    assert db_check is db_check_impl
    assert make_nas_testset is testset


def test_without_a_command_it_prints_the_usage(capsys):
    assert main([]) == 2
    out = capsys.readouterr().out
    assert out.startswith(f"usage: {PROG} COMMAND")
    for name in ("copy-check", "db-check", "make-test-set"):
        assert name in out
    assert main(["--help"]) == 0
    assert capsys.readouterr().out.strip() == usage()
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"{PROG} {__version__}"


def test_an_unknown_command_is_a_usage_error(capsys):
    assert main(["copy"]) == 2
    assert "unknown command 'copy'" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["copy-check", "db-check", "make-test-set"])
def test_each_command_has_help_under_its_own_name(capsys, command):
    assert main([command, "--help"]) == 0
    assert capsys.readouterr().out.startswith(f"usage: {PROG} {command}")


def test_db_check_create_and_check(tmp_path, capsys):
    path = tmp_path / "scratch.db"
    assert main(["db-check", "create", str(path)]) == 0
    assert database_status(path) is SchemaStatus.CURRENT
    assert main(["db-check", "check", str(path)]) == 0
    assert capsys.readouterr().out.rstrip().endswith("RESULT PASS")


def test_copy_check_with_a_made_source(tmp_path, capsys):
    code = main(
        [
            "copy-check",
            str(tmp_path / "dest"),
            "--make-source",
            str(tmp_path / "work"),
            "--files",
            "2",
            "--file-mb",
            "0.01",
            "--workers",
            "1",
            "2",
            "--fsync",
            "on",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.count("PASS") == 2
    assert (tmp_path / "dest" / "workers-2-fsync-on" / "0" / "1790733601.dat").is_file()


def test_make_test_set_refuses_a_used_folder(tmp_path, capsys):
    used = tmp_path / "used"
    used.mkdir()
    (used / "keep.txt").write_text("x", encoding="utf-8")
    assert main(["make-test-set", str(used), "--quick"]) == 1
    assert "must be new or empty" in capsys.readouterr().err
    assert sorted(p.name for p in used.iterdir()) == ["keep.txt"]


def test_a_usage_error_inside_a_command_returns_2(capsys):
    assert main(["db-check", "hold"]) == 2  # no PATH
    assert "error" in capsys.readouterr().err
