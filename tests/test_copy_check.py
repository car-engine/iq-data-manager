"""Tests for tools/copy_check.py. Source and destination live in tmp_path."""

from pathlib import Path

import copy_check


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = copy_check.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_copies_and_verifies_for_each_worker_count(tmp_path, capsys):
    work, dest = tmp_path / "work", tmp_path / "dest"
    code, out, _ = run(
        capsys,
        str(work),
        str(dest),
        "--files",
        "5",
        "--file-mb",
        "0.01",
        "--workers",
        "1",
        "3",
        "--hash",
    )
    assert code == 0
    lines = [line for line in out.splitlines() if line.startswith(("PASS", "FAIL"))]
    assert len(lines) == 2
    assert all(line.startswith("PASS") for line in lines)
    source = sorted(p.name for p in (work / "source" / "0").iterdir())
    assert len(source) == 5
    for n in (1, 3):
        copied = sorted(p.name for p in (dest / f"workers-{n}" / "0").iterdir())
        assert copied == source
    first = work / "source" / "0" / source[0]
    assert first.stat().st_size == 10_000
    assert (dest / "workers-1" / "0" / source[0]).read_bytes() == first.read_bytes()
    assert "Remove" in out


def test_folders_must_be_new_or_empty(tmp_path, capsys):
    work = tmp_path / "work"
    work.mkdir()
    (work / "x.txt").write_text("x", encoding="utf-8")
    code, _, err = run(capsys, str(work), str(tmp_path / "dest"), "--file-mb", "0.001")
    assert code == 2
    assert "WORK_DIR must be a new or empty folder" in err
    assert not (tmp_path / "dest").exists()


def test_arguments_must_be_positive(tmp_path, capsys):
    code, _, err = run(capsys, str(tmp_path / "w"), str(tmp_path / "d"), "--files", "0")
    assert code == 2
    assert "must be positive" in err


def test_a_destination_that_is_not_empty_is_refused(tmp_path, capsys):
    dest = tmp_path / "dest"
    (dest / "workers-1").mkdir(parents=True)
    code, _, err = run(capsys, str(tmp_path / "work"), str(dest), "--file-mb", "0.001")
    assert code == 2
    assert "DEST_DIR must be a new or empty folder" in err
    assert not (tmp_path / "work").exists()


def test_a_repeated_worker_count_runs_once(tmp_path, capsys):
    code, out, _ = run(
        capsys,
        str(tmp_path / "work"),
        str(tmp_path / "dest"),
        "--files",
        "2",
        "--file-mb",
        "0.001",
        "--workers",
        "2",
        "2",
    )
    assert code == 0
    assert sum(line.startswith("PASS") for line in out.splitlines()) == 1
    assert "SKIP   2 at once" in out


def test_the_tool_has_a_docstring_with_usage():
    assert "Usage:" in (copy_check.__doc__ or "")
    assert Path(copy_check.__file__).name == "copy_check.py"
