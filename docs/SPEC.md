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
   ranges to a local PC. The app copies the files itself, with a preview before and a
   verification after each transfer (DECISIONS.md D48).

A fourth tab, **Settings**, edits the per-machine configuration and shows the state
of the database (section 4; DECISIONS.md D29).

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
  For NAS folders the app stores and uses UNC paths: it replaces a mapped drive letter
  with the share's UNC path (DECISIONS.md D14). A folder on a laptop's own disk keeps
  its drive path.
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
| `recordings` | One row per capture session: envelope times, site, file format, storage location, archive state, plan reference, remarks, and `created_at` and `updated_at` (a trigger sets `updated_at` on every update; the Viewer shows it, D47). |
| `channels` | One row per channel: index, subfolder, band, fc, fs, own start/end, file count, bytes. Single-channel recordings have one row (index 0). |
| `recording_params` | Flexible RF chain key/value rows. `channel_id` NULL = whole recording, set = one channel. |
| `transfer_log` | History of moves, copies, archive checks and deletions of laptop copies, including time ranges, channel subset, hash mode, verification result and the path of each transfer's manifest. A delete row names the move it follows in `parent_id` (D52). |

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
The Settings tab writes it with `tomli-w` (see "Settings tab" below; DECISIONS.md D29,
D31).

A missing file gives the defaults, which have no `db_path`. Unknown keys are ignored
when the file is read, and kept when the Settings tab writes it (DECISIONS.md D15).
`--config PATH` reads and writes another file, and `--db PATH` overrides `db_path`.

```toml
db_path = '\\192.168.1.50\recordings\iq_catalog.db'
default_local_copy_root = 'D:\work\iq'
network_speed_mb_s = 110          # used for time estimates
default_hash_mode = "sample"      # "none" | "sample" | "all"
hash_sample_fraction = 0.05
nas_roots = ['\\192.168.1.50\recordings']   # UNC roots; a folder under one is on the NAS (D14)
display_utc_offset_hours = 8      # displayed times only; -12 to 14 in steps of 0.25 (D24)
coverage_highlight_percent = 99   # the Viewer marks coverage below this; above 0, at most 100 (D39)
free_space_margin_gb = 10         # kept free on a transfer destination; 0 or more (D51)

[storage_roots]                    # UNC root -> local path override (Linux later)
# '\\192.168.1.50\recordings' = '/mnt/nas/recordings'
```

### Settings tab (Milestone 3a)

A fourth tab, "Settings", after "Move / copy" (DECISIONS.md D29, D30). It edits
`config.toml` and shows the state of the database. Decisions D31 to D38 settle its
details. The milestone is "Milestone 3a" (D32). Its text follows CLAUDE.md, "User-facing
text": no key names, decision numbers or database internals on screen (D38).

| Section | Fields and actions |
| --- | --- |
| Database | "Database file" (`db_path`), with Browse for an existing `.db` file. A status line in green, amber or red with a mark (D38): ready to use; no path, checking, or a newer database the app can only read; missing, a folder, unreadable, not an IQ Data Manager database, or an older database. The tooltip holds the schema version and connection settings (`connection.inspect_database()`). The check runs when the tab opens, after Browse, when the path field loses focus, and on "Check connection". It uses a read-only connection. |
| NAS locations | The `nas_roots` list, with Add, Edit and Remove. Each entry must pass `config.is_unc_path()`. A line explains the rule in plain words: folders under these locations count as already archived on the NAS (D14, D2). |
| Display | "Show times at UTC offset" (`display_utc_offset_hours`), from −12 to 14 in steps of 0.25 (D24), with an example such as "2026-09-30 02:00:00 UTC is shown as 2026-09-30 10:00:00 (UTC+8)." "Highlight coverage below" (`coverage_highlight_percent`), from 0.0 to 100.0 % with one decimal place; 0 is an error (Milestone 4, D39). |
| About | The path of the settings file in use, with "Open folder". The app version. A note when `--config` or `--db` is in force. |

The tab shows these four keys only (D34). Milestone 3a added the first three, and
Milestone 4 added the coverage threshold (D39). Keys that later milestones need are
added to the tab by those milestones: `default_local_copy_root`,
`network_speed_mb_s`, `default_hash_mode`, `hash_sample_fraction` and
`free_space_margin_gb` (Milestone 6; Milestone 5 reads them from the file only).

Not in the Settings tab (D30):

- **"Upgrade database".** It waits for the first real schema migration (O19). Until
  then an older database gives a red status line that says this version of the app
  cannot open it (D37, D38).
- **Data-file extensions.** They stay fixed in code as `.dat` and `.bin`
  (`scanner.DEFAULT_EXTENSIONS`, any letter case), so every PC scans a folder the same
  way. A new extension comes with a new release.
- **Creating a database.** The real catalogue comes from the legacy migration tool
  (Milestone 7). An empty database comes from `tools/db_check.py create`. Milestone 7
  adds an admin command-line option, `--create-db PATH`, for packaged builds.

Behaviour:

- **Validation.** Every field is checked by the same rules as
  `config.parse_config()`. A wrong value is marked at its field, and Save stays
  disabled until it is fixed. Save is also disabled while nothing has changed.
- **A wrong key the tab does not show** keeps Save disabled. The tab names the key.
  The user corrects it in the file by hand and clicks "Reload from file" (D36).
- **Writing.** Save writes `config.toml` with `tomli-w` (D31). It creates
  `%APPDATA%\IQDataManager` if the folder is missing. It writes `config.toml.new` in
  the same folder and then replaces the old file with it, so a failed write leaves the
  old file intact. The previous file is kept as `config.toml.bak`, replaced on each
  Save (D35).
- **Keys the tab does not show** stay in the file, for example `storage_roots` and any
  key added by hand. Comments in the file are lost on write. The tab says so.
- **Applying.** Changes apply on Save, without a restart (D33). A new display offset
  redraws the Log tab's times and keeps its form. A new `db_path` or new NAS roots
  clear the Log tab form and reload its lists. If the form holds input that is not
  saved, the app asks first, and No writes nothing. While the Log tab saves a
  recording, the Settings tab does not save. The Viewer takes a new offset,
  threshold or `db_path` at once and asks nothing, because it holds no input
  (section 5).
- **Overrides.** `--config` and `--db` keep working. With `--db`, Save writes
  `db_path` to the file, and the `--db` path stays in force for the current run. The
  tab says so.
- **Startup errors.** A configuration file that cannot be read opens the app on the
  Settings tab with the error shown, so the user can correct it there. A file that is
  not valid TOML can be replaced by Save.
- **Database files.** The Settings tab never creates or changes a database (D30). It
  opens the chosen file read-only.
- **Architecture.** The writer and its validation live in `config.py` (no Qt). The tab
  is `gui/settings_tab.py`. Database checks run in the `TaskRunner`, because a
  database on the NAS can take seconds to answer.
- **Tests.** Configuration files are written only under `tmp_path`. Database checks
  use databases under `tmp_path`, including one set to an older and one to a newer
  `user_version` for the status line.

## 5. Tab: Viewer

Built in Milestone 4. The logic lives in `viewer.py` (no Qt), the tab in
`gui/viewer_tab.py`. Its text follows CLAUDE.md, "User-facing text" (D38).

- **Filters** (D43): start date from and to (`YYYY-MM-DD` at the display offset; the
  "to" date includes its whole day), site, band, centre frequency range in MHz (band
  and range match on the same channel), archive state, "RF chain contains" (a
  parameter's name, value or unit) and "Remarks contain". Filters apply on Apply or
  Enter, and Clear removes them. A wrong value is marked under the filters and runs
  no query. The filter runs in SQL (D40).
- **Recordings table**: ID, start at the display offset, site, channel count, centre
  frequencies in MHz ("433.92 × 2" when all channels share one), span, coverage
  (minimum across channels), total size, archive state, logged by. Every column
  sorts, numbers as numbers. The model sorts its own rows (D40).
- **Marks**: coverage below `coverage_highlight_percent` is amber with the ⓘ mark
  (D39). An archived recording logged in place on the NAS shows "archived, not
  verified" in amber (D2, D44). A coverage or size that the database does not hold
  shows "unknown".
- Selecting a recording shows its channels table (index, band, fc, fs, start, end,
  files, coverage) and the details panel for the recording. Selecting a channel
  narrows the details to that channel.
- **Details panel**: the RF chain that applies (Recording rows, with a channel's own
  rows replacing Recording rows of the same name and naming the replaced value; D28),
  full path of the recording or channel, format, plan reference, remarks, who logged
  it and when, when it last changed (`updated_at`, shown when it differs from the
  logging time; D47), the "not verified" note, and the transfer history.
- **Gap detail** (section 7): "Scan for gaps" reads the recording folder in a worker
  with the stored file duration, with progress and Cancel. It shows a coverage
  timeline per channel, the gaps per channel at the display offset (the first 10,
  then a count), and where the folder differs from the database: a channel missing on
  either side, a different file count or a different total size. The scan writes
  nothing.
- **Actions** on the selected recording: Refresh (keeps the filter, the sort order
  and the selection), Open folder (the recording folder, or the channel folder when a
  channel is selected), Edit entry (D45: opens the Log tab in edit mode, and asks
  first when the Log tab form holds input that is not saved). Copy / move comes with
  the Move / copy tab in Milestone 6 (D42). The GUI does not delete recordings (D41).
- **Database states**: no database path gives a line that points to the Settings
  tab. A database from a newer app version is shown with an amber line (D6). A file
  that is missing, older or not an IQ Data Manager database gives a red line with the
  technical text in its tooltip.
- **Configuration**: a saved new display offset, threshold or database path applies
  at once (D33). A new database path clears the tab and loads the new list.
- Read-only. Every query uses a read-only connection. Refresh queries again; the tab
  holds no connection open. The Viewer also refreshes after a Log tab save (D46).

## 6. Tab: Log recording

Flow: choose folder, scan, review and complete fields, validate, save.

1. **Source folder**: browse to a recording folder (local or on the NAS; DECISIONS.md
   D18). "Scan folder" runs the scanner (section 7) in a worker thread. The tab shows
   the number of files found so far and has a Cancel button.
2. **Recording fields**: start and end (from scan, read-only, at the display offset,
   UTC+8 by default; D24), file duration (default 1.0 s), logged by (pre-filled with
   the Windows login name, editable), site (dropdown plus "Add site"), recording plan
   reference, storage root and relative path (derived from the folder, read-only),
   archive state (derived: `local` unless the folder is under a configured NAS root,
   then `archived`; see DECISIONS.md D2 for the `transfer_log` row written in that
   case), remarks. Read-only fields look different from editable ones in the light and
   the dark theme.

   Storage root and relative path follow D14. A mapped drive letter is replaced by
   its UNC path. Under a NAS root, the root is the configured NAS root and the
   relative path is the rest. Elsewhere, the root is the parent folder and the
   relative path is the folder name. A drive root, a share root and a NAS root
   itself cannot be logged.
3. **File format**: sample type (`int8`, `int16` default, `float32`), IQ layout
   (`interleaved_iq` default, `interleaved_qi`, `planar_iq`), endianness (little
   default), header bytes (0, at the start of every file).
4. **Channels**: one row per detected channel with folder, start, end, files and
   coverage from the scan; band, fc and fs from the user. Band is an optional editable
   dropdown that lists the bands already in the DB. fc is entered in MHz (D19). fs
   takes a number with an optional unit: none or `Hz`, `k` or `kHz`, `M` or `MHz`,
   `G` or `GHz`, with or without a space (D25); the app fills it in after a scan (see
   below). Both are stored in Hz, converted through `Decimal`.
5. **RF chain**: editable rows of applies-to (Recording / Ch N), parameter, value,
   unit. Parameter names autocomplete from values already in the DB.

   A Recording row is the value for every channel without a row of its own (D28).
   Names compare without letter case and are saved with the spelling already in the
   DB. In one scope, the same name with two different values is an error, and a
   repeated row is saved once. A channel row that repeats or overrides the Recording
   value is information.

Validation before save (shown as a checklist):

- Folder scanned and contains at least one channel with files.
- Folder not already logged (`UNIQUE (storage_root, rel_path)`).
- File sizes consistent with fs: expected bytes per file =
  `header_bytes + fs_hz * file_duration_s * 2 * bytes_per_sample`. A channel's last
  file may be shorter than expected; that is reported as information (DECISIONS.md
  D3). A last file of `header_bytes` bytes or fewer holds no IQ data and is an error
  (D13). Any other mismatch, including a last file larger than expected, is an error
  that names the channel and the expected and actual sizes.
- Required fields present; fc and fs positive.
- Gaps are reported as information, not errors.
- File duration within 1 % of the median step between file timestamps (D22).
- Channel coverage at most 100.0 % (D22).

Each checklist item is ok, information, to do or error (D23). To do marks a field
still to fill in. Error marks a wrong value or a folder that cannot be logged as it
stands. Saving needs no to-do item and no error.

Values filled in after a scan:

- **fs** for each channel, from the typical file size, the sample type, the header
  bytes and the file duration (D21). The header is never guessed and defaults to 0.
  A filled-in fs is shown in italics and follows the format fields until the user
  types in it.
- **File duration**, from the median step between file timestamps (D22), until the
  user changes the field. Edit mode keeps the stored duration.

Choosing another folder for a new entry resets the file duration, the file format,
the channel rows and the RF chain rows to their defaults (D26). Logged by, site,
plan reference and remarks stay.

A folder named like a channel folder (1 to 3 digits, such as `0`) gets an
information line and a "Use parent folder" button. It does not block saving (D27).

Save writes the recording, channels and params in one transaction and confirms it in a
pop-up. Edit mode loads an existing recording into the same form and updates it.

Edit mode (DECISIONS.md D16):

- It opens from the "Edit existing entry" button, shown when a scanned folder is
  already logged, and from the Viewer in Milestone 4 (`LogTab.load_recording()`).
- The folder, storage root, relative path, archive state and `archived_at` stay as
  stored. A save in edit mode writes no `transfer_log` row. A save that changes no
  value writes nothing and says "No changes to save." (D47).
- Logged by, site, plan reference, remarks, IQ layout, endianness, band, fc and the
  RF chain save without a rescan.
- A change to fs, sample type, header bytes or file duration needs a rescan first.
- A rescan that removes channels asks for confirmation on save. The dialog names the
  channels and the number of their parameters.
- The rescan removes the RF chain rows of those channels from the form at once
  (D20). Rows for the whole recording and for other channels stay.

## 7. Scanner

Pure-Python module (`src/iqdm/scan/scanner.py`), no GUI imports. Input: a recording
folder path and file duration. Output: a result with a dataclass per channel and a
list of unrecognised entries.

- Channel detection: subfolders named with a canonical decimal number (`0`, `1`,
  `12`) are channels. `channel_index` is the folder number, so folders `0` and `2`
  give channels 0 and 2 (DECISIONS.md D11). If there are none and the folder itself
  contains data files, it is channel 0 with `sub_path = ''`. An empty channel folder
  is a channel with no files.
- Data files: names whose stem parses as a Unix timestamp (integer, optionally with a
  fractional part: `^\d+(\.\d+)?$`), extensions `.dat` and `.bin` in any letter case
  (fixed in code; DECISIONS.md D30). Other files, other subfolders, folders inside a
  channel folder and symbolic links are ignored and listed as "unrecognised" in the
  result.
- Scan errors (D11): data files in the recording folder next to channel folders; a
  numeric folder name with a leading zero, such as `01`; two files in one channel with
  the same timestamp value. The scan stops and lists every such problem.
- Per channel: sorted timestamps, first and last, `n_files`, `total_bytes`, set of
  distinct file sizes, the size of the last file (DECISIONS.md D3), and gaps as a list
  of `(start_unix, missing_seconds)` runs. A gap exists where consecutive timestamps
  differ by more than 1.5 × `file_duration_s`, and it is a whole number of missing
  files (D12).
- Channel check: given fs, sample type and header size, reports the size errors and
  information in section 6, a channel with no files, and files closer together than
  half the file duration (D11, D12, D13).
- Uses `os.scandir` for speed and takes file sizes from the directory entries; must
  handle tens of thousands of files per channel. Reports progress and can be
  cancelled.
- **Gap detail**: gaps are not stored in the DB. The viewer computes them on demand
  with a "Scan" action; transfer previews compute them for the selected range.

## 8. Tab: Move / copy

Milestone 5 builds the transfer core in `src/iqdm/transfer/` without a GUI. Milestone 6
builds the tab over it.

### Operations

- **Copy to a local PC**: source is a recording (usually archived on the NAS). The
  recording entry is unchanged; a `transfer_log` row is added with `operation =
  'copy'`.
- **Archive to the NAS (move)**: source is a `local` recording on the laptop, whole,
  with all channels, and its folder must match the database entry (D50). Steps: copy,
  verify, then on success update `storage_root`, `rel_path`,
  `archive_state = 'archived'` and `archived_at` in the same transaction that
  finishes the `transfer_log` row. A failed verification leaves the recording `local`.
  If another move archived the recording while this one ran, this move is logged as
  failed, and the recording keeps the first archive copy.
- **Delete the laptop copy**: a separate, explicit, user-confirmed action, offered
  only after a move passed verification. It is logged as a `transfer_log` row with
  `operation = 'delete'` and the move in `parent_id` (D52).
- **Check archive**: compare an archived recording's folder with its database entry:
  channels, and file count and total size per channel. It is logged with
  `operation = 'check'`. Counts the database does not hold (legacy entries) are
  filled in from the folder, and that check is logged as `'skipped'`. A folder that
  cannot be scanned is a failed check.

Each copy or move first writes its `transfer_log` row with `started_at`. A row with no
`finished_at` is a transfer that never completed, for example after a crash. A
cancelled transfer is finished with `verification = 'skipped'` and a note.

### Scope

- Whole recording, or a time range. A file at time `t` is in the range when
  `start <= t < end` (D49). Input is UTC date-time or Unix time, kept in sync.
- Channel checkboxes: any subset of the recording's channels.
- Timeline showing the selected range against each channel's available data and gaps.

### Selection

`transfer/selection.py`. Before every transfer the app rescans the source folder with
the scanner (D53). The rescan gives the real file names, the size of each file and the
gaps. The selection holds, per channel, the files in the range, their total size and
the missing seconds inside the range (D49). It also lists where the folder differs
from the database entry.

### Copy engine

`transfer/copier.py` copies the selection itself (D48). There are no scripts.

- Each file is copied in chunks to `<name>.partial` in its destination folder, with
  missing folders created. When the copy is complete, the file gets the source's
  modification time and is renamed to its real name. The rename never replaces an
  existing file.
- A target file that already exists with the source's size counts as copied and is
  skipped (resume, D51). A target file with another size makes the destination check
  refuse the transfer. If one appears after the check, the engine leaves it alone and
  the transfer is logged as failed.
- Before the rename, each file is flushed to the destination's disks (`os.fsync`).
  A crash at the destination then cannot leave a file with its real name and size
  but without its data. `copy_files(fsync=False)` exists for timing comparisons
  only (D54).
- Each file gets up to 3 retries after the first attempt, 5 s apart.
- Progress reports files and bytes. Cancel stops between chunks and leaves the
  `.partial` file, which a later run overwrites.
- The engine can compute the source's SHA-256 while it copies, and can copy several
  files at once.
- A dry run is the preview: it computes the selection, the destination checks and the
  estimate, and writes nothing.
- `transfer/power.py` keeps Windows from sleeping while a transfer runs.

### Manifest

After each copy or move that passes verification, the app writes a manifest (D52): a
JSON file in the `manifests` folder next to the configuration file, named
`transfer-<id>-<finish time>.json`, for example `transfer-7-20261003T080000Z.json`.
It lists each file's relative path (`/`-separated), size and SHA-256 where one was
computed, with the transfer's source, destination, range and channels. It is written
only to a new file. A move's destination is stored as its NAS location, with a mapped
drive letter replaced by the UNC path (D14), so the log row, the manifest and the
recording name the same folder. `transfer_log.manifest_path` holds its path and
`transfer_log.manifest_sha256` the SHA-256 of its bytes.

### Transfer safety

- **Destination validation** (`transfer/pathcheck.py`): not a drive root or a share
  root, not equal to or inside the source, source not inside the destination. Paths
  compare without letter case. A move needs a destination that is new, empty, or
  holds only the target files of an interrupted move of the same selection. A copy
  also accepts a destination that holds other files (D51). Free space must cover the
  bytes still to copy plus `free_space_margin_gb`. Paths must stay within the Windows
  limits (259 characters for a file, 247 for a folder) unless long paths are enabled.
  An archive destination must lie under a NAS root, at a location no other recording
  uses (D50).
- **Preview** before running: file count, total size, missing seconds per channel,
  estimated time from `network_speed_mb_s` and for the chosen hash mode, the
  destination checks, and the file list.
- **Verification** (`transfer/verify.py`): always compare the count and each file's
  size between the selection and the destination. Optional SHA-256 by `hash_mode`:
  `none`; `sample`, which hashes `ceil(hash_sample_fraction × n)` files, at least one,
  chosen as the files whose relative path has the smallest SHA-256; or `all`. Source
  hashes come from the copy where it computed them. Files in the destination that are
  not in the selection are reported and do not fail the verification.
- **Deletion**: all deletion goes through `src/iqdm/transfer/delete.py` (D52). It
  needs a move with a passed verification and a manifest whose SHA-256 matches. The
  recording must point at the move's destination. Right before each source file is
  deleted, its destination copy and the source file must still have the manifest
  size. It deletes only the files in the manifest, never whole trees by pattern, and
  then removes folders that are empty. The result is logged as a delete row.

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
    app.py                    # QApplication, main window and its tabs, --config/--db
    config.py                 # TOML config load and save (Settings tab, D31), defaults
    models.py                 # dataclasses: Recording, Channel, Param, TransferEntry...
    timeutil.py               # UTC ISO 8601 text <-> Unix seconds; display offset (D24)
    location.py               # folder -> storage_root, rel_path, archive state (D14)
    entry.py                  # Log tab logic: form input, checklist, save (no Qt)
    viewer.py                 # Viewer logic: filters, table text, details, gap lines (no Qt)
    db/
      schema.sql
      version.py              # LATEST_VERSION and schema_status(), shared by the two below
      connection.py           # connect(), read-only connect, retry-on-lock helper
      migrations.py           # user_version-based migrations, backup before migrate
      repository.py           # all queries and writes
    scan/
      scanner.py
    transfer/
      selection.py            # rescan + range + channels -> file list, gaps (D53)
      pathcheck.py            # destination validation
      manifest.py             # per-file manifest, written once (D52)
      copier.py               # the copy engine (D48)
      verify.py               # count/size/hash verification
      delete.py               # the only module that deletes files
      estimate.py             # size/time estimates
      operations.py           # copy, move, check and delete flows with their log rows
      power.py                # keeps Windows awake during a transfer
    gui/
      viewer_tab.py
      log_tab.py
      transfer_tab.py
      settings_tab.py         # Settings tab (section 4, D29)
      workers.py              # QThread/QRunnable wrappers
      widgets/                # timeline, checklist, param table, recordings table model
  tools/
    make_fixtures.py          # synthetic IQ recordings for tests and manual testing
    db_check.py               # create, write and locking checks on a scratch database (O21)
    copy_check.py             # copy-engine throughput, flush on and off (D48, D54)
    make_nas_testset.py       # synthetic recordings for the NAS field test (D54)
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
  optional header, optional wrong-size file, and tone, zero, random or empty content.
  Used by pytest fixtures via `tmp_path`. `tools/make_nas_testset.py` builds the NAS
  field test set from it (D54).
- Unit tests for scanner, selection, gap detection, manifest, path validation,
  estimates, the copy engine, verification, deletion, repository and migrations.
- The copy engine, verification and deletion run on synthetic recordings under
  `tmp_path`. Tests never run robocopy or any script.
- GUI tests use `pytest-qt` on Qt's offscreen platform. Logic that needs no Qt is
  tested without it (`entry.py` for the Log tab). GUI tests drive the real widgets,
  wait for the `TaskRunner`, and replace modal dialogs with stubs. They also check
  colours against a light and a dark palette.
- `tests/test_architecture.py` enforces the module rules in section 9 by reading the
  package source (DECISIONS.md D10).
- `tests/test_user_text.py` checks the visible text of each tab for decision numbers,
  SPEC references, config key names and database internals (DECISIONS.md D38).

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

   3a. **Settings tab** (brought forward from Milestone 7; DECISIONS.md D29): config
   writer, Settings tab with database status and check, NAS roots and display
   offset, applying changes without a restart, tests (scope narrowed by D30).
4. **Viewer tab**: filters, recordings table, channels, details, actions.
5. **Transfer core**: selection, path checks, manifest, copy engine (D48), estimates,
   verification, delete module, and the copy, move, check and delete flows with their
   `transfer_log` rows. No GUI. Heavily tested.
6. **Move / copy tab**: GUI over the core, preview, run with progress and cancel,
   post-verification delete flow, the transfer keys in the Settings tab. The
   Viewer's Copy / move button comes with this tab (D42). The milestone ends with the
   first test on the NAS, with the test set from `tools/make_nas_testset.py` (D54).
7. **Packaging and migration**: PyInstaller build, legacy migration tool (packaged, so
   it runs without Python), an admin option `--create-db PATH` for an empty database,
   short user guide (D30). The settings dialog and the config writer moved to
   Milestone 3a (D29).

## 13. Scope

Out of scope for v1: Linux build, transfer scripts (D48), file-level gap storage in
the DB, user accounts, editing RF chain templates, deleting catalogue entries from the
GUI (D41).

Open questions and assumptions that may still change are listed in `docs/STATUS.md`.
Resolved decisions are in `docs/DECISIONS.md`.
