# IQ Data Manager: specification

This file states the current requirements. Related documents:

- `docs/DECISIONS.md`: resolved questions, with dates and reasons. References such
  as "DECISIONS.md D2" point there.
- `docs/STATUS.md`: milestone progress, open questions and pending checks.
- `docs/reports/`: one report per milestone.

## 1. Purpose

The team records raw RF IQ data (SDRs such as the USRP X310) as one-second binary files
named by Unix time, e.g. `1790733600.dat`. Recordings are later archived on NAS
storage and sometimes copied back to local PCs for processing. Today, metadata is
logged into a shared SQLite database by hand (MATLAB/Python scripts), and files are
moved with copy-paste or ad-hoc robocopy scripts.

This app replaces both with one Windows desktop tool with three tabs:

1. **Viewer**: browse and filter recordings, their channels and RF chain details.
2. **Log recording**: scan a recording folder and add it to the database.
3. **Move / copy**: archive recordings to the NAS, or copy whole recordings or time
   ranges to a local PC, via previewed and verified generated scripts.

Mockups of all three tabs exist on a design canvas, with exports in `docs/mockup/`;
this document is the source of truth where they differ.

## 2. Environment and constraints

- **Platform**: Windows 10/11 first. Linux support is planned later, so all
  business logic must be OS-agnostic (see section 9).
- **Language / GUI**: Python 3.12, PySide6. Packaged with PyInstaller as a onedir
  build (a folder holding the executable), built on Windows (DECISIONS.md D8).
- **Database**: one master SQLite file on a NAS SMB share, accessed directly by every
  PC. Practically one writer at a time; occasional concurrent readers. No
  authentication beyond network access.
- **Storage**: NAS shares reached over gigabit Ethernet, usually as mapped drives.
  The app stores and uses UNC paths, not drive letters.
- **Data**: raw complex IQ, typically int16 interleaved I then Q, little-endian.
  Allowed sample types are `int8`, `int16` and `float32` (DECISIONS.md D1). Some
  recordings have a fixed-size header at the start of every file. Sample rates from
  kHz to tens of MHz; at 50 MS/s a one-second file is 200 MB. Recordings range up to
  1 TB per folder. Files may be missing (gaps) inside a recording.
- **Multi-channel**: multi-channel captures store each channel in a numbered
  subfolder (`<recording>/0/`, `<recording>/1/`). Single-channel recordings may have
  files directly in the recording folder or in `0/`.

## 3. Database

Schema: `src/iqdm/db/schema.sql` (authoritative). Summary:

| Table | Purpose |
| --- | --- |
| `sites` | Selectable site names, unique case-insensitively. Users can add new ones. |
| `recordings` | One row per capture session: envelope times, site, file format, storage location, archive state, plan reference, remarks. |
| `channels` | One row per channel: index, subfolder, band, fc, fs, own start/end, file count, bytes. Single-channel recordings have one row (index 0). |
| `recording_params` | Flexible RF chain key/value rows. `channel_id` NULL = whole recording, set = one channel. |
| `transfer_log` | History of moves, copies and archive checks, including time ranges, channel subset, hash mode and verification result. |

Key semantics:

- **Times** are UTC. `start_unix` is the first file's timestamp. `end_unix` is
  exclusive: last file's timestamp + `file_duration_s`. Span = `end - start`.
  Recording-level times are the envelope across its channels.
- **Coverage** for a channel = `n_files * file_duration_s / (end_unix - start_unix)`.
  Recording coverage shown in the viewer is the minimum across its channels.
- **Location**: `storage_root` is a UNC root (e.g. `\\192.168.1.50\recordings`), or
  the laptop folder while `archive_state = 'local'`. `rel_path` is relative to it.
  Full path = `storage_root / rel_path`, channel path adds `channels.sub_path`.
- **Archive state**: `local` (data only on the recording laptop) or `archived` (on
  the NAS and verified). The app sets `archived` only after verification passes, with
  one exception. A folder logged in place on the NAS is set to `archived` without
  verification, and its log entry marks it as unverified (DECISIONS.md D2).
- **Deletion**: `channels` and `recording_params` cascade on recording delete.
  `transfer_log` does not, so a recording with transfer history cannot be deleted
  without explicit handling.
- **Schema version**: `PRAGMA user_version`. Changes are numbered migrations in
  `src/iqdm/db/migrations.py`. They run only from an explicit, user-confirmed
  upgrade action, with a backup copy made first (DECISIONS.md D6). Until the first
  real database exists, `schema.sql` is edited in place as version 1 (D4).

### DB access rules

- Every connection: `PRAGMA foreign_keys = ON`, `PRAGMA busy_timeout = 5000`, default
  rollback journal (never WAL on an SMB share).
- Open, do the work, close. Never hold a connection open while the GUI is idle.
- Writes are short transactions with retry and backoff on `database is locked`, then
  a clear error to the user. Attempts and pauses are in DECISIONS.md D7.
- The viewer opens connections read-only (`file:...?mode=ro` URI).

## 4. Configuration

Per-machine TOML file at `%APPDATA%\IQDataManager\config.toml`, read with `tomllib`.
Created with defaults on first run; editable from a small settings dialog.

```toml
db_path = '\\192.168.1.50\recordings\iq_catalog.db'
default_local_copy_root = 'D:\work\iq'
network_speed_mb_s = 110          # used for time estimates
default_hash_mode = "sample"      # "none" | "sample" | "all"
hash_sample_fraction = 0.05

[storage_roots]                    # UNC root -> local path override (Linux later)
# '\\192.168.1.50\recordings' = '/mnt/nas/recordings'
```

## 5. Tab: Viewer

- Filters: start date range, site, band, centre frequency range, archive state, text
  search in RF chain values, text search in remarks.
- Recordings table: ID, start (UTC+8), site, channel count, centre frequencies, span,
  coverage (minimum across channels, highlighted below a threshold such as 99%),
  total size, archive state, logged by. Sortable columns.
- Selecting a recording shows its channels table (index, band, fc, fs, start, end,
  files, coverage) and a coverage timeline per channel if gap data is available
  (see section 7, "Gap detail").
- Selecting a channel shows the details panel: RF chain parameters (recording-wide
  and that channel's), full path, format, plan reference, remarks, transfer history.
- Actions on the selected recording: Refresh, Open folder (Explorer), Edit entry
  (opens Log tab in edit mode), Copy / move (opens Move / copy tab pre-selected).
- Read-only. Refresh re-queries; no live connection.

## 6. Tab: Log recording

Flow: choose folder, scan, review and complete fields, validate, save.

1. **Source folder**: browse to a recording folder (local or on the NAS). "Scan
   folder" runs the scanner (section 7) in a worker thread with progress.
2. **Recording fields**: start and end (from scan, read-only), file duration (default
   1.0 s), logged by (pre-filled with the Windows login name, editable), site
   (dropdown plus "Add site"), recording plan reference, storage root and relative
   path (derived from the folder, read-only), archive state (derived: `local` unless
   the folder is under a configured NAS root, then `archived`; see DECISIONS.md D2 for
   the `transfer_log` row written in that case), remarks.
3. **File format**: sample type (`int8`, `int16` default, `float32`), IQ layout
   (`interleaved_iq` default, `interleaved_qi`, `planar_iq`), endianness (little
   default), header bytes (0, at the start of every file).
4. **Channels**: one row per detected channel with folder, start, end, files and
   coverage from the scan; band, fc (MHz in the UI, Hz in the DB) and fs entered by
   the user.
5. **RF chain**: editable rows of applies-to (Recording / Ch N), parameter, value,
   unit. Parameter names autocomplete from values already in the DB.

Validation before save (shown as a checklist):

- Folder scanned and contains at least one channel with files.
- Folder not already logged (`UNIQUE (storage_root, rel_path)`).
- File sizes consistent with fs: expected bytes per file =
  `header_bytes + fs_hz * file_duration_s * 2 * bytes_per_sample`. A channel's last
  file may be shorter than expected; that is reported as information (DECISIONS.md
  D3). Any other mismatch, including a last file larger than expected, is an error
  that names the channel and the expected and actual sizes.
- Required fields present; fc and fs positive.
- Gaps are reported as information, not errors.

Save writes the recording, channels and params in one transaction. Edit mode loads an
existing recording into the same form and updates it.

## 7. Scanner

Pure-Python module, no GUI imports. Input: a recording folder path and file
duration. Output: a dataclass per channel.

- Channel detection: numeric subfolders (`0`, `1`, ...) are channels. If there are
  none and the folder itself contains data files, it is channel 0 with
  `sub_path = ''`.
- Data files: names whose stem parses as a Unix timestamp (integer, optionally with a
  fractional part), extensions `.dat` and `.bin` (configurable). Other files are
  ignored and counted as "unrecognised" in the result.
- Per channel: sorted timestamps, first and last, `n_files`, `total_bytes`, set of
  distinct file sizes, the size of the last file (DECISIONS.md D3), and gaps as a list
  of `(start_unix, missing_seconds)` runs.
- Uses `os.scandir` for speed; must handle tens of thousands of files per channel.
- **Gap detail**: gaps are not stored in the DB. The viewer computes them on demand
  with a "Scan" action; transfer previews compute them for the selected range.

## 8. Tab: Move / copy

### Operations

- **Copy to a local PC**: source is a recording (usually archived on the NAS). The
  recording entry is unchanged; a `transfer_log` row is added with `operation =
  'copy'`.
- **Archive to the NAS (move)**: source is a `local` recording on the laptop. Steps:
  copy, verify, then on success update `storage_root`, `rel_path`,
  `archive_state = 'archived'`, `archived_at`, and log the transfer. Deleting the
  laptop copy is a separate, explicit, user-confirmed action offered only after
  verification passes, and is itself logged in `transfer_log.notes`.
- **Check archive**: verify an archived recording on the NAS against its DB entry
  (count and size per channel, optional hashes), logged with `operation = 'check'`.

### Scope

- Whole recording, or a time range (start inclusive, end exclusive), entered as UTC
  date-time or Unix time, kept in sync.
- Channel checkboxes: any subset of the recording's channels.
- Timeline showing the selected range against each channel's available data and gaps.

### Script generation

Behind one interface (`ScriptGenerator`), with a Windows implementation now and a
Linux (rsync) implementation later.

- Whole recording, all channels: robocopy with `/E /COPY:DAT /R:3 /W:5 /MT:8 /NP
  /LOG+:<logfile>` (tune `/MT` in testing). Never `/MIR` or `/PURGE`.
- Time range or channel subset: a manifest file listing relative paths
  (`<sub_path>\<timestamp>.dat`), one per line, plus a PowerShell script that reads it
  and copies each file, creating folders as needed. This avoids command-length limits
  and handles gaps naturally.
- Scripts start with a comment header: operation, recording ID, range, channels,
  generated time, app version.
- Both can be saved to disk for the user to run, or run by the app (subprocess with
  argument lists, output streamed to a progress view, cancellable).
- Dry run: robocopy `/L`, or a manifest check that lists what would be copied, with
  missing source files reported.

### Transfer safety

- Destination validation: not a drive root, not equal to or inside the source,
  source not inside the destination, destination empty or new, enough free space
  (with a margin), path length under limits or long-path support enabled.
- Preview before running: file count, total size, missing seconds per channel,
  estimated time from `network_speed_mb_s`, full script text and manifest preview.
- Verification: always compare file count and per-file size between source selection
  and destination. Optional SHA-256 (`hash_mode`: none, sample fraction, all), read in
  chunks, with estimated added time shown beforehand.
- All deletion goes through one module (`src/iqdm/transfer/delete.py`) that requires
  a passed verification record for exactly the files being deleted, deletes only
  those files (never whole trees by pattern), and logs the result.

## 9. Architecture

```
iq-data-manager/
  CLAUDE.md
  pyproject.toml
  requirements.txt            # pinned runtime deps
  requirements-dev.txt        # pytest, ruff, pyinstaller
  .claude/                    # Claude Code settings and safety hook
  docs/
    SPEC.md                   # current requirements (this file)
    DECISIONS.md              # decision log D1, D2, ...
    STATUS.md                 # progress, open questions, pending checks
    REPORT_TEMPLATE.md        # format of milestone reports
    reports/                  # one report per milestone: M0.md, M1.md, ...
    KICKOFF.md                # session start-up and resume prompts
    mockup/                   # exported GUI mockups
  src/iqdm/
    __main__.py               # python -m iqdm
    app.py                    # QApplication, main window with three tabs
    config.py                 # TOML config load/save, defaults
    models.py                 # dataclasses: Recording, Channel, Param, Transfer...
    timeutil.py               # UTC ISO 8601 text <-> Unix seconds
    db/
      schema.sql
      version.py              # LATEST_VERSION and schema_status(), shared by the two below
      connection.py           # connect(), read-only connect, retry-on-lock helper
      migrations.py           # user_version-based migrations, backup before migrate
      repository.py           # all queries and writes
    scan/
      scanner.py
    transfer/
      selection.py            # resolve range + channels -> file list, gaps
      pathcheck.py            # destination validation
      manifest.py
      scripts/
        base.py               # ScriptGenerator interface
        windows.py            # robocopy + PowerShell/manifest
      runner.py               # subprocess execution, progress, cancel
      verify.py               # count/size/hash verification
      delete.py               # the only module that deletes files
      estimate.py             # size/time estimates
    gui/
      viewer_tab.py
      log_tab.py
      transfer_tab.py
      settings_dialog.py
      workers.py              # QThread/QRunnable wrappers
      widgets/                # timeline, checklist, param table, etc.
  tools/
    make_fixtures.py          # synthetic IQ recordings for tests and manual testing
    migrate_legacy.py         # legacy DB -> new schema (writes a NEW file)
  tests/
  build/
    iqdm.spec                 # PyInstaller spec
```

Rules: nothing outside `gui/` and `app.py` imports PySide6. All SQL lives in `db/`,
and only `db/` imports `sqlite3` (DECISIONS.md D7). `transfer/delete.py` is the only
place that deletes files.

## 10. Legacy data migration

The current database has one table with columns `date, date_unix, site, band, fc_hz,
fs_hz, duration_s, data_dir, remarks`. `tools/migrate_legacy.py` reads a copy of it
and writes a new database file; it never modifies the original.

Mapping: distinct `site` values become `sites` rows; each row becomes one recording
(`start_unix = date_unix`, `end_unix = date_unix + duration_s`, `archive_state =
'archived'`, `logged_by = 'legacy-import'`, format defaults) plus one channel row
(index 0, `band`, `fc_hz`, `fs_hz`, same times, `n_files` and `total_bytes` NULL).
`data_dir` is split into `storage_root` and `rel_path` using configured UNC roots and
a drive-letter-to-UNC mapping supplied as arguments. Rows that cannot be mapped are
written to a report, not guessed. A later "Check archive" fills in counts and sizes.

## 11. Testing

- `tools/make_fixtures.py` creates synthetic recordings in a given folder: N channels,
  duration, fs (small, e.g. 1 kS/s so files are tiny), gaps at chosen seconds,
  optional header, optional wrong-size file. Used by pytest fixtures via `tmp_path`.
- Unit tests for scanner, selection, gap detection, manifest, script text, path
  validation, estimates, verification, repository and migrations.
- Script generators are tested on their text output only. Tests never execute
  robocopy or generated scripts.
- `runner.py` is tested with a fake command (e.g. a tiny Python script) inside
  `tmp_path`.
- GUI smoke tests with `pytest-qt` are optional and limited to construction and basic
  wiring.
- `tests/test_architecture.py` enforces the module rules in section 9 by reading the
  package source (DECISIONS.md D10).

## 12. Milestones

Each milestone ends with passing tests, `ruff check` clean, a commit, and a report in
`docs/reports/` that follows `docs/REPORT_TEMPLATE.md`. Progress is tracked in
`docs/STATUS.md`.

0. **Scaffold**: pyproject, requirements, package layout, ruff and pytest config,
   empty three-tab main window, `make_fixtures.py`, PyInstaller smoke build.
1. **Database layer**: connection helpers, schema creation, migrations framework,
   repository with CRUD for all tables, retry-on-lock, tests.
2. **Scanner**: channel detection, file listing, gaps, sizes, fs consistency check,
   tests on fixtures including large synthetic file counts (empty files are fine).
3. **Log tab**: form, scan worker, validation checklist, save and edit mode.
4. **Viewer tab**: filters, recordings table, channels, details, actions.
5. **Transfer core**: selection, path checks, manifest, script generators, estimates,
   verification, delete module. No GUI. Heavily tested.
6. **Move / copy tab**: GUI over the core, dry run, run with progress and cancel,
   transfer logging, archive state update, post-verification delete flow.
7. **Packaging and migration**: settings dialog, config file, PyInstaller build,
   legacy migration tool, short user guide.

## 13. Scope

Out of scope for v1: Linux build, rsync generator, file-level gap storage in the DB,
user accounts, editing RF chain templates.

Open questions and assumptions that may still change are listed in `docs/STATUS.md`.
Resolved decisions are in `docs/DECISIONS.md`.
