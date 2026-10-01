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

## Run

```
python -m iqdm
```
