# IQ Data Manager

A Windows desktop app that logs RF IQ recordings into a shared SQLite database and
copies and archives them with verification. Version 1.0.0 is released; its notes for
the team are in `docs/RELEASE_NOTES.md`. Start with `docs/HANDOFF.md` when you pick up
the repository. Requirements are in `docs/SPEC.md`, decisions in `docs/DECISIONS.md`,
and progress and open questions in `docs/STATUS.md`. Development rules are in
`CLAUDE.md`.

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

## Check tools

Each tool prints its usage with `--help` and deletes nothing. Use them only on scratch
databases and folders. The code lives in `src/iqdm/diagnostics/`; the scripts in
`tools/` are wrappers over it (DECISIONS.md D57). The packaged build runs the same
code as `IQDataManager-check.exe COMMAND`, in a console window.

| Tool | Packaged command | Use |
| --- | --- | --- |
| `tools/db_check.py` | `db-check` | Create a scratch database; check opening, writing and locking (O21). Refuses a database with recordings it did not write. |
| `tools/copy_check.py` | `copy-check` | Time the copy engine with 1, 4 and 8 files at once, flush on and off. |
| `tools/make_nas_testset.py` | `make-test-set` | Write the synthetic recordings for the NAS field test (D54). |
| `tools/migrate_legacy.py` | `migrate-legacy` | Import a copy of the legacy catalogue into a new database (D66, D71). Opens the legacy file read-only; `--dry-run` writes nothing. |

## Run

Create a development database first. The command refuses a file that exists. Until
the version 1 schema is frozen (O20), `schema.sql` is edited in place, and the app
refuses a database made before such an edit as an older version (D73). Make a new
one under a new name after such an edit.

```
python tools/db_check.py create dev/scratch.db
```

```
python -m iqdm
python -m iqdm --smoke-test        # builds the window, quits, exit code 0 on success
python -m iqdm --db dev/scratch.db # uses this database instead of db_path in the config
python -m iqdm --config my.toml
```

The app reads `%APPDATA%\IQDataManager\config.toml`. Without the file, the app has
no database: the Viewer lists nothing and the Log tab cannot save. Set the database
file and the NAS locations in the Settings tab and click Save. The tab writes the
file and keeps the previous one as `config.toml.bak` (DECISIONS.md D31, D35). The
keys are in `docs/SPEC.md` section 4.

The file can also be written by hand. A minimal file:

```toml
db_path = 'D:\iq\catalog.db'
nas_roots = ['\\nas\recordings']   # UNC roots; a folder under one is logged as archived
```

Use single quotes, so TOML keeps the backslashes. A Save from the Settings tab drops
comments.

## Build

`build/iqdm.spec` makes a onedir build with two programs: the windowed
`IQDataManager.exe` and the console program `IQDataManager-check.exe` (D57). The
build folder also holds `USER_GUIDE.md`, `RELEASE_NOTES.md` and
`defaults.example.toml` (D68). Build into output folders that do not exist yet. Do not pass `--noconfirm` or `--clean`,
because both delete existing output.

```
PYINSTALLER_CONFIG_DIR=build/pyinstaller-cache pyinstaller build/iqdm.spec --distpath dist/<name> --workpath build/work-<name>
dist/<name>/IQDataManager/IQDataManager.exe --smoke-test
dist/<name>/IQDataManager/IQDataManager-check.exe --help
```

Both executables must declare long-path support in their manifest (D65). This
command prints one line for each executable, ending in `true</longPathAware>`:

```
grep -a -o "<longPathAware[^<]*</longPathAware>" dist/<name>/IQDataManager/*.exe
```

`PYINSTALLER_CONFIG_DIR` keeps PyInstaller's cache inside the repository. Git ignores
`build/` (except the spec) and `dist/`. Remove old build output by hand.
