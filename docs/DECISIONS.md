# IQ Data Manager: decision log

This file records resolved questions about requirements and design, with the date
and the milestone in which each was decided. `docs/SPEC.md` states the current
requirements and points here for the reasons. Open questions are listed in
`docs/STATUS.md` until they are decided.

Rules for this file:

- Decision numbers are permanent. Entries are never renumbered. Code comments and
  commit messages refer to them, for example "DECISIONS.md D4".
- A new decision gets the next free number, even if it concerns an earlier
  milestone. D8 to D10 record Milestone 0 choices that were written down later.
- A decision that is reversed stays in the file. Its status changes to "Replaced by
  Dn", and the new entry explains the change.
- After adding or changing a decision, update the affected sections of `SPEC.md` so
  the spec states the current requirement.

| No. | Title | Decided | Status |
| --- | --- | --- | --- |
| D1 | Sample types | 2026-10-02, before Milestone 1 | Active |
| D2 | Logging a folder that is already on the NAS | 2026-10-02, before Milestone 1 | Active |
| D3 | Short last file | 2026-10-02, before Milestone 1 | Active |
| D4 | Schema baseline | 2026-10-02, Milestone 1 | Active |
| D5 | Transfer log columns | 2026-10-02, Milestone 1 | Active |
| D6 | Running migrations | 2026-10-02, Milestone 1 | Active |
| D7 | Database layer defaults | 2026-10-02, Milestone 1 | Active |
| D8 | PyInstaller onedir build | 2026-10-02, Milestone 0 | Active |
| D9 | Qt package | 2026-10-02, Milestone 0 | Active |
| D10 | Architecture tests read the package source | 2026-10-02, Milestone 0 | Active |
| D11 | Scanner folder rules | 2026-10-02, Milestone 2 | Active |
| D12 | Gap rule | 2026-10-02, Milestone 2 | Active |
| D13 | Last file without IQ data | 2026-10-02, Milestone 2 | Active |
| D14 | Recording folder location | 2026-10-02, Milestone 3 | Active |
| D15 | Reading the configuration in Milestone 3 | 2026-10-02, Milestone 3 | Active |
| D16 | Edit mode in the Log tab | 2026-10-02, Milestone 3 | Active |
| D17 | Times in the Log tab | 2026-10-02, Milestone 3 | Active |
| D18 | Logging any folder | 2026-10-02, Milestone 3 | Active |
| D19 | Band and frequency input | 2026-10-02, Milestone 3 | Active |
| D20 | RF chain rows of channels removed by a rescan | 2026-10-02, Milestone 3 | Active |

## D1. Sample types

- Data is always complex IQ, so the size formula in SPEC section 6 keeps the
  factor 2.
- Allowed `dtype` values are `int8`, `int16` and `float32`, with 1, 2 and 4 bytes per
  sample. The default is `int16`.
- `int8` covers the USRP `sc8` wire format. `float32` is allowed in the schema. Whether
  down-converted float32 data belongs in this catalogue is a team policy question.
- `uint8` and packed sub-byte formats (4-bit, 2-bit) are out of scope.
- A header, when present, sits at the start of every file. `header_bytes` is its size.
- `schema.sql` enforces the list with `CHECK (dtype IN ('int8', 'int16', 'float32'))`,
  added in Milestone 1.

Affects: SPEC sections 2 and 6, `schema.sql`, `models.SampleType`.

## D2. Logging a folder that is already on the NAS

- Data reaches the NAS by manual copy. Nobody records straight to the NAS.
- Logging a folder under a configured NAS root sets `archive_state = 'archived'`. The
  same transaction writes a `transfer_log` row with these values:
  - `operation = 'check'`
  - `verification = 'skipped'`
  - `source` = the folder's full path
  - `destination` = NULL
  - `performed_by` = the logged-by name
  - `notes = 'logged in place, not verified against a source'`
- The Viewer reads this row and marks the recording as unverified. The schema has no
  separate archive state for this case.
- Laptop copies are deleted only when the storage space is needed, so the laptop copy
  often still exists when a NAS folder is logged. Milestone 6 reconsiders a "verify
  against source" action for this case. That milestone also decides how a later
  verification clears the unverified mark.

Affects: SPEC sections 3 and 6. Tested in `tests/test_repository.py`.

## D3. Short last file

- The first file of a channel is never short. A short first file is an error.
- A channel's last file may be shorter than expected when a capture stops mid-file.
  The Log tab reports it as information. A last file larger than expected is an
  error, as is a size mismatch in any other file.
- The short last file counts as one file in `n_files`. `end_unix` keeps its
  definition (last file's timestamp + `file_duration_s`), so span and coverage are
  slightly overstated for that channel.
- The scanner reports the size of each channel's last file separately from the set of
  distinct sizes.

Affects: SPEC sections 6 and 7.

## D4. Schema baseline

- No database uses the new schema yet. The first real database is created by the
  legacy migration in Milestone 7.
- Until then, `schema.sql` is edited in place and stays at `user_version = 1`.
- From the first real database on, every schema change is a numbered migration.

Affects: SPEC section 3, `schema.sql`, `db/migrations.py`.

## D5. Transfer log columns

- `transfer_log.channels` records the channel subset: NULL for all channels, else
  sorted indices separated by commas, e.g. `'0,2'`.
- `transfer_log.hash_mode` records the verification hash mode: `none`, `sample` or
  `all`. It is NULL when no verification ran.
- Source deletion stays recorded in `transfer_log.notes` (SPEC section 8). A
  structured deletion record and a per-file verification manifest are reconsidered in
  Milestone 5.

Affects: SPEC sections 3 and 8, `schema.sql`, `db/repository.py`.

## D6. Running migrations

- The app never migrates on startup. When the database version is older than the
  app's, the app refuses to write and offers an "Upgrade database" action.
- The upgrade asks for confirmation, writes a backup next to the database through
  SQLite's online backup API, and never overwrites an existing backup file.
- Each migration step runs in its own transaction and sets `user_version` inside it.
  A failed step leaves the database at the last good version.
- Reads are allowed on a database newer than the app, with a warning. Reads are
  refused on an older database. Writes need the current version.

Affects: SPEC section 3, `db/connection.py`, `db/migrations.py`.

## D7. Database layer defaults

- The repository derives `recordings.date`, `start_unix` and `end_unix` from the
  channel rows. `date` is `start_unix` as ISO 8601 UTC, in whole seconds.
- Triggers reject a `recording_params.channel_id` that belongs to a different
  recording.
- `archived_at` is set exactly when `archive_state = 'archived'` (CHECK constraint).
  Logging in place (D2) and the legacy import set it to the time the row is written.
- A parameter names its channel by `channel_index` in the app. The repository maps
  the index to `channel_id`.
- Editing a recording updates channels in place by `channel_index` and inserts new
  ones. Removing a channel needs an explicit flag, because it deletes that channel's
  parameters. Parameters are replaced as a set.
- Write retry: `busy_timeout = 5000`, 3 attempts, pauses of 1 s and 2 s between
  them. The worst case is about 18 s before the error is shown.
- Channel coverage is undefined (NULL in the app) when `n_files` is NULL or the span
  is zero.
- Sites can be added and listed. The app has no rename or delete for sites.
- All SQL lives in `src/iqdm/db/`, as CLAUDE.md states. This replaces the earlier
  spec rule that `db/repository.py` is the only place with SQL, because
  `connection.py` and `migrations.py` also need SQL. An architecture test checks that
  only `db/` imports `sqlite3`.

Affects: SPEC sections 3 and 9, `schema.sql`, `db/`, `models.py`.

## D8. PyInstaller onedir build

- The spec asked for a single executable. The build is onedir instead: a folder that
  holds `IQDataManager.exe` and its libraries.
- Reasons: faster start, no unpacking to `%TEMP%` on every launch, and fewer
  antivirus false positives. The folder can be zipped for distribution.
- Builds go into output folders that do not exist yet. `--noconfirm` and `--clean`
  are never used, because both delete existing output. `README.md` has the commands.

Affects: SPEC section 2, `build/iqdm.spec`.

## D9. Qt package

- The runtime dependency is `PySide6-Essentials` (QtCore, QtGui, QtWidgets), which
  covers everything the spec needs. The coverage timeline is a custom-painted widget.
- Full `PySide6`, which adds the Addons package, would be a new dependency. It needs
  approval, for example if QtCharts becomes necessary.

Affects: `requirements.txt`, `pyproject.toml`.

## D10. Architecture tests read the package source

- CLAUDE.md says no test may read or write outside its temp directory.
  `tests/test_architecture.py` is an approved exception. It reads
  `src/iqdm/**/*.py` with `ast` and writes nothing.
- It checks three module boundaries: PySide6 only in `gui/` and `app.py`, `sqlite3`
  only in `db/`, and `.unlink()` and `.rmdir()` calls only in `transfer/delete.py`.
- Ruff's banned-API rule (TID251 in `pyproject.toml`) covers the deletion functions
  in `os` and `shutil`.

Affects: `tests/test_architecture.py`, `pyproject.toml`.

## D11. Scanner folder rules

Closes O4 (M0 review 16).

- A subfolder is a channel folder when its name is a canonical decimal number: `0`,
  `1`, `12`. `channel_index` is the folder number, so folders `0` and `2` give
  channels 0 and 2. `sub_path` is the folder name.
- The scan stops with an error in three cases:
  - data files sit in the recording folder next to channel folders;
  - a numeric folder name has a leading zero, such as `01`;
  - two data files in one channel have the same timestamp value, for example
    `1790733600.dat` and `1790733600.bin`, or `1790733600.dat` and
    `1790733600.0.dat`.
- The error lists every such problem in the folder. The folder cannot be logged
  until someone fixes it.
- A data file stem matches `^\d+(\.\d+)?$`. Extensions match in any letter case.
- Other files, other subfolders, folders inside a channel folder and symbolic links
  are listed as unrecognised.
- An empty channel folder is a channel with no files. The channel check reports it
  as an error.
- The channel check combines all wrong-size files of a channel into one finding. The
  finding gives the count and the names and sizes of the first 10 files.
- A single file that is shorter than expected is a short first file, so it is an
  error (D3).

Affects: SPEC section 7, `scan/scanner.py`.

## D12. Gap rule

Closes O5 (M0 review 17).

- Two consecutive timestamps `t1 < t2` in one channel differ by `d = t2 - t1`.
- A gap exists where `d > 1.5 * file_duration_s`. Smaller differences are jitter.
- The gap starts at `t1 + file_duration_s`.
- `missing_seconds = (n - 1) * file_duration_s`, where `n` is `d / file_duration_s`
  rounded to the nearest whole number, with halves rounded up. A gap is therefore
  always a whole number of missing files.
- Where `d < 0.5 * file_duration_s`, the channel check reports an error and asks the
  user to check the file duration.

Affects: SPEC section 7, `scan/scanner.py`.

## D13. Last file without IQ data

Closes O24 (Milestone 2 report, issue 2). Narrows D3.

- A last file whose size is `header_bytes` or less holds no IQ data. The channel check
  reports it as an error, together with the other wrong-size files.
- The user asked for an error when the size is below the header size. The rule uses
  "or less" because a file of exactly `header_bytes` bytes also holds no IQ data, and
  with no header a 0-byte file would otherwise pass.
- A last file larger than `header_bytes` and smaller than expected stays information
  (D3).

Affects: SPEC sections 6 and 7, `scan/scanner.py`.

## D14. Recording folder location

Closes O2 (M0 review 10) and O3 (M0 review 11).

- A folder path is first normalised: backslashes, no trailing separator.
- The drive letter of a mapped network drive is replaced by the drive's UNC path. The
  app reads the drive mapping with `WNetGetConnectionW` through `ctypes`. This call
  opens no folder.
- The configuration lists the NAS roots in a new key, `nas_roots`. Each entry is a UNC
  path.
- A folder under a NAS root gets these values:
  - `storage_root` = the NAS root as written in the configuration, without a
    trailing separator;
  - `rel_path` = the rest of the path;
  - `archive_state = 'archived'`, with the `transfer_log` row from D2.
- The match ignores letter case and compares whole path components, so
  `\\nas\rec` does not match `\\nas\recordings2`. When two roots match, the longer
  one wins.
- Any other folder is local: `storage_root` = the parent folder, `rel_path` = the
  folder name, `archive_state = 'local'`.
- A network folder outside every NAS root is local by the rule above. The Log tab
  reports it as information.
- `rel_path` is stored with backslashes, like the UNC roots and the legacy
  `data_dir` values.
- A drive root, a UNC share root and a NAS root itself cannot be logged as a
  recording folder.

Affects: SPEC sections 4 and 6, `location.py`, `config.py`.

## D15. Reading the configuration in Milestone 3

Narrows O18 for Milestone 3. O18 stays open for Milestone 7.

- `config.py` reads `%APPDATA%\IQDataManager\config.toml` with `tomllib`. It never
  writes the file.
- A missing file gives the defaults. The default has no database path, so the Log
  tab cannot save until the user adds `db_path` to the file by hand.
- A file that is not valid TOML, or a key with a wrong type or value, is an error
  that names the file and the key. Unknown keys are ignored.
- Two command-line options exist for development and manual tests. `--config PATH`
  reads another configuration file. `--db PATH` overrides `db_path`.
- Writing the file, and creating it with defaults on first run, stay in O18
  (Milestone 7).

Affects: SPEC section 4, `config.py`, `app.py`.

## D16. Edit mode in the Log tab

Closes O14 (M0 review 20). Builds on D7.

- `LogTab.load_recording(recording_id)` opens edit mode. In Milestone 3 the Log tab
  offers it when a scanned folder is already logged. In Milestone 4 the Viewer's
  "Edit entry" action calls it.
- The folder cannot change in edit mode. `storage_root`, `rel_path`,
  `archive_state` and `archived_at` keep their stored values. A save in edit mode
  writes no `transfer_log` row.
- These fields save without a rescan: logged by, site, recording plan reference,
  remarks, IQ layout, endianness, band, fc and the RF chain.
- A change to fs, sample type, header bytes or file duration needs a rescan of the
  stored folder before the save, so the size check can run.
- After a rescan, the channel rows take their start, end, file count and size from
  the scan.
- A rescan that removes channels is allowed. On save, a dialog names the removed
  channels and the number of their parameters. "Yes" calls
  `update_recording(..., allow_channel_removal=True)`. "No" writes nothing.

Affects: SPEC section 6, `entry.py`, `gui/log_tab.py`.

## D17. Times in the Log tab

Narrows O1 for Milestone 3. O1 stays open for Milestones 4 and 6.

- The Log tab shows every time in UTC, and each label says "(UTC)".
- The config key for a display offset (UTC+8) is not added in Milestone 3. The
  Viewer decides it in Milestone 4.

Affects: SPEC section 6, `gui/log_tab.py`.

## D18. Logging any folder

Closes O23 (former SPEC section 13).

- The Log tab logs a folder on a local disk or on the NAS.
- A scan runs in a worker thread. The tab shows the number of files found so far and
  has a Cancel button, because a scan over the network takes longer.

Affects: SPEC section 6.

## D19. Band and frequency input

- Band is an editable dropdown. Its list holds the bands already in the database.
  Band is optional, as the schema allows NULL.
- fc and fs are entered in MHz and stored in Hz.
- The conversion goes through `Decimal`, so a decimal entry such as `145.8` gives
  exactly 145 800 000 Hz.

Affects: SPEC section 6, `entry.py`, `db/repository.py`.

## D20. RF chain rows of channels removed by a rescan

Closes issue 1 of the Milestone 3 report. Adds to D16.

- In the first build of edit mode, the RF chain rows of a removed channel stayed in
  the form. The checklist reported each row as an error, so the user had to remove
  the rows by hand before the D16 dialog appeared.
- Now a rescan in edit mode removes those rows from the form at once and says so in
  the tab's message line. Rows for the whole recording and for other channels stay.
- The D16 dialog on save stays the only confirmation. "No" writes nothing, and the
  stored rows come back when the user opens the entry again.

Affects: SPEC section 6, `entry.py`, `gui/log_tab.py`.
