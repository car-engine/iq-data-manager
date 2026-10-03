"""Tests for tools/copy_check.py. Sources and destinations live in tmp_path."""

import copy_check


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = copy_check.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def result_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith(("PASS", "FAIL"))]


def test_made_source_is_copied_for_each_worker_count_and_flush(tmp_path, capsys):
    work, dest = tmp_path / "work", tmp_path / "dest"
    code, out, _ = run(
        capsys,
        str(dest),
        "--make-source",
        str(work),
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
    lines = result_lines(out)
    assert len(lines) == 4
    assert all(line.startswith("PASS") for line in lines)
    assert "flush on " in lines[0] and "flush off" in lines[1]
    assert "ms/file" in lines[0]
    source = sorted(p.name for p in (work / "source" / "0").iterdir())
    assert len(source) == 5
    assert (work / "source" / "0" / source[0]).stat().st_size == 10_000
    runs = sorted(p.name for p in dest.iterdir())
    assert runs == [
        "workers-1-fsync-off",
        "workers-1-fsync-on",
        "workers-3-fsync-off",
        "workers-3-fsync-on",
    ]
    for name in runs:
        assert sorted(p.name for p in (dest / name / "0").iterdir()) == source


def test_an_existing_recording_is_the_source(tmp_path, capsys, make_recording):
    info = make_recording(n_channels=2, n_slots=3, junk=True)
    dest = tmp_path / "dest"
    code, out, _ = run(capsys, str(dest), "--source", info.root, "--workers", "2", "--fsync", "on")
    assert code == 0
    assert len(result_lines(out)) == 1
    copied = dest / "workers-2-fsync-on"
    assert (copied / "0" / "1790733600.dat").read_bytes() == (
        tmp_path / "rec0" / "0" / "1790733600.dat"
    ).read_bytes()
    assert (copied / "notes.txt").exists()  # every file under the source is copied


def test_a_repeated_worker_count_runs_once(tmp_path, capsys, make_recording):
    info = make_recording(n_slots=2)
    code, out, _ = run(
        capsys,
        str(tmp_path / "dest"),
        "--source",
        info.root,
        "--workers",
        "2",
        "2",
        "--fsync",
        "off",
    )
    assert code == 0
    assert len(result_lines(out)) == 1


def test_folders_must_be_new_or_empty(tmp_path, capsys):
    work = tmp_path / "work"
    work.mkdir()
    (work / "x.txt").write_text("x", encoding="utf-8")
    code, _, err = run(capsys, str(tmp_path / "dest"), "--make-source", str(work))
    assert code == 2
    assert "WORK_DIR must be a new or empty folder" in err
    dest = tmp_path / "used"
    (dest / "workers-1-fsync-on").mkdir(parents=True)
    code, _, err = run(capsys, str(dest), "--make-source", str(tmp_path / "w2"))
    assert code == 2
    assert "DEST_DIR must be a new or empty folder" in err
    assert not (tmp_path / "w2").exists()


def test_a_missing_or_empty_source_is_refused(tmp_path, capsys):
    code, _, err = run(capsys, str(tmp_path / "d"), "--source", str(tmp_path / "missing"))
    assert (code, "does not exist" in err) == (2, True)
    (tmp_path / "empty").mkdir()
    code, _, err = run(capsys, str(tmp_path / "d"), "--source", str(tmp_path / "empty"))
    assert (code, "holds no files" in err) == (2, True)


def test_arguments_must_be_positive(tmp_path, capsys):
    code, _, err = run(
        capsys, str(tmp_path / "d"), "--make-source", str(tmp_path / "w"), "--files", "0"
    )
    assert code == 2
    assert "must be positive" in err


def test_a_source_is_required(tmp_path):
    import pytest

    with pytest.raises(SystemExit):
        copy_check.main([str(tmp_path / "d")])
