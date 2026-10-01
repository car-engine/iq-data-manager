# IQ Data Manager

A Windows desktop app that logs RF IQ recordings into a shared SQLite database and
generates verified copy and archive operations. Requirements are in `docs/SPEC.md`.
Development rules are in `CLAUDE.md`.

## Set up

Use Python 3.12 in a virtual environment at the repository root.

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --no-cache-dir -r requirements-dev.txt
pip install --no-cache-dir --no-deps -e .
```

`requirements.txt` and `requirements-dev.txt` hold exact pins. `pyproject.toml` holds
only the loose runtime range.

## Test and lint

```
pytest
ruff check
```

GUI tests run on Qt's offscreen platform, so no window opens.

## Synthetic recordings

`tools/make_fixtures.py` creates synthetic IQ recordings. Tests use it through the
`make_recording` fixture in `tests/conftest.py`, which writes under `tmp_path`. For
manual testing, write under `fixtures_out/`, which git ignores:

```
python tools/make_fixtures.py fixtures_out/demo --channels 2 --gap 3-4 --junk
python tools/make_fixtures.py --help
```

The tool only creates files. It refuses an output folder that exists and is not empty.

## Run

```
python -m iqdm
```
