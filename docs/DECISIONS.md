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
| D15 | Reading the configuration in Milestone 3 | 2026-10-02, Milestone 3 | Active; the app writes the file since D31 |
| D16 | Edit mode in the Log tab | 2026-10-02, Milestone 3 | Active |
| D17 | Times in the Log tab | 2026-10-02, Milestone 3 | Replaced by D24 |
| D18 | Logging any folder | 2026-10-02, Milestone 3 | Active |
| D19 | Band and frequency input | 2026-10-02, Milestone 3 | Active; fs input replaced by D25 |
| D20 | RF chain rows of channels removed by a rescan | 2026-10-02, Milestone 3 | Active |
| D21 | fs from the file size | 2026-10-02, Milestone 3 | Active |
| D22 | File duration from the file names; coverage above 100 % | 2026-10-02, Milestone 3 | Active |
| D23 | To-do items in the checklist | 2026-10-02, Milestone 3 | Active |
| D24 | Display offset for times | 2026-10-02, Milestone 3 | Active |
| D25 | fs input with units | 2026-10-02, Milestone 3 | Active |
| D26 | Folder fields reset for a new folder | 2026-10-02, Milestone 3 | Active |
| D27 | Warning for a folder named like a channel folder | 2026-10-02, Milestone 3 | Active |
| D28 | RF chain repeats, overrides and conflicts | 2026-10-02, Milestone 3 | Active |
| D29 | Settings tab before the Viewer | 2026-10-02, after Milestone 3 | Active; scope narrowed by D30 |
| D30 | Settings scope: no upgrade button, fixed extensions, no database creation | 2026-10-02, after Milestone 3 | Active |
| D31 | Writing config.toml with tomli-w | 2026-10-02, Milestone 3a | Active |
| D32 | Name of the Settings milestone | 2026-10-02, Milestone 3a | Active |
| D33 | Applying settings without a restart | 2026-10-02, Milestone 3a | Active |
| D34 | Keys in the Settings tab | 2026-10-02, Milestone 3a | Active |
| D35 | Backup of config.toml | 2026-10-02, Milestone 3a | Active |
| D36 | A wrong value in a key the Settings tab does not show | 2026-10-02, Milestone 3a | Active |
| D37 | Status line for an older database | 2026-10-02, Milestone 3a | Replaced by D38 |
| D38 | Plain text for users; coloured database status | 2026-10-03, Milestone 3a | Active |
| D39 | Coverage highlight threshold | 2026-10-03, Milestone 4 | Active |
| D40 | Recordings list at the size of the catalogue | 2026-10-03, Milestone 4 | Active |
| D41 | No deletion of recordings in the GUI | 2026-10-03, Milestone 4 | Active |
| D42 | No Copy / move button in the Viewer before Milestone 6 | 2026-10-03, Milestone 4 | Active |
| D43 | Viewer filters | 2026-10-03, Milestone 4 | Active |
| D44 | The "not verified" mark in the Viewer | 2026-10-03, Milestone 4 | Active |
| D45 | Edit entry with unsaved input in the Log tab | 2026-10-03, Milestone 4 | Active |
| D46 | The Viewer refreshes after a Log tab save | 2026-10-03, Milestone 4 | Active |
| D47 | When a recording last changed | 2026-10-03, Milestone 4 | Active |

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

## D21. fs from the file size

The user found the empty fs fields alarming after a scan (manual test, 2026-10-02).

- After a scan, the Log tab fills each channel's fs:
  fs = (typical file size − header bytes) / (2 × bytes per sample × file duration).
- The typical file size is the most common size in the channel, leaving out the last
  file (D3). Ties go to the larger size.
- The header is never guessed. Header bytes default to 0, as the file duration
  defaults to 1 s and the sample type to `int16`. The user changes them by hand.
- A filled-in fs is shown in italics with a tooltip. The checklist names its basis:
  file size, duration, sample type and header. It asks the user to check the value
  against the recording plan.
- A filled-in fs follows the sample type, header bytes and file duration until the
  user types in the field. From then on the typed value stays.
- When the typical file is not a whole number of complex samples after the header,
  fs stays empty and the checklist says why.
- Edit mode never replaces a stored fs. Only a channel that a rescan adds gets a
  filled-in value.
- Known limits, accepted by the user:
  - The size check cannot catch a wrong filled-in fs. It still finds files that
    differ from the typical size.
  - Sample type and fs trade off exactly. A 200,000,000-byte 1 s file is 100 MS/s as
    `int8`, 50 MS/s as `int16` or 25 MS/s as `float32`. The user must set the sample
    type.
  - A wrong header gives a wrong fs in the same way.

Affects: SPEC section 6, `entry.py`, `gui/log_tab.py`.

## D22. File duration from the file names; coverage above 100 %

- The median step between consecutive file timestamps, over all channels, is the
  file duration the names show. Gaps barely move a median. The value is rounded to
  1 µs.
- After a scan of a new entry, the Log tab sets the file duration to that value
  until the user changes the field. A value other than 1 s adds an information
  line.
- A file duration that differs from the median step by more than 1 % is an error.
  This covers a duration the user set and a stored duration in edit mode after a
  rescan.
- Channel coverage above 100.0 %, at one decimal place, is an error in every case.
  Coverage above 100 % means that the files overlap in time.
- Reason: with D21 alone, 0.5 s files logged at the default 1 s gave a filled-in fs
  of half the true rate, an all-green checklist and 195 % coverage.

Affects: SPEC section 6, `entry.py`, `gui/log_tab.py`.

## D23. To-do items in the checklist

- A checklist item has one of four states: ok, information, to do and error.
- To do (grey) is a field still to fill in: the folder still to scan, the
  logged-by name, the site, empty fc or fs, and an RF chain row without a name or
  value. Empty fc and fs give one line per field that lists the channels.
- Error (red) is a value that is wrong, or a folder that cannot be logged as it
  stands. A scan that stopped is an error that lists its problems. A channel with no
  files is an error before fs is entered.
- Saving needs no to-do item and no error.

Affects: SPEC section 6, `entry.py`, `gui/widgets/checklist.py`.

## D24. Display offset for times

Replaces D17. Closes the display part of O1. O1 stays open for time input in the Move /
copy tab (Milestone 6).

- The user asked for start and end times at UTC+8 after the first manual test.
- A new config key, `display_utc_offset_hours`, sets the offset for displayed times.
  The default is 8. Allowed values run from −12 to 14 in steps of 0.25.
- Every displayed time shows its zone, for example "Start (UTC+8)" or "UTC+5:30".
  With an offset of 0 the label is "UTC".
- The offset comes from the configuration, never from the PC's time zone.
- Storage is unchanged: the database holds UTC text and Unix seconds.

Affects: SPEC sections 4, 5 and 6, `config.py`, `timeutil.py`, `gui/log_tab.py`.

## D25. fs input with units

Replaces the fs part of D19. fc stays in MHz.

- The user found that counting decimal places in MHz is error-prone at low sample
  rates.
- The fs field takes a number with an optional unit. No unit means Hz.
- Accepted units: `Hz`; `k` and `kHz`; `M` and `MHz`; `G` and `GHz`. A space between
  the number and the unit is optional, so `100 M` and `100M` are both accepted.
- Letter case matters. `m` would read as milli, so only `M` means mega. Any other
  unit is an error that lists the accepted forms.
- `Hz` was not in the user's list. The agent added it because the app displays fs
  with a unit, for example `500 Hz`, and must read its own text back.
- The app shows a filled-in or stored fs in the largest unit that keeps the number
  at 1 or more: `1 kHz`, `12.5 kHz`, `50 MHz`.
- The conversion goes through `Decimal`, so `12.5k` gives exactly 12 500 Hz.
- fc keeps MHz without a unit. A bare number in fc read as Hz would turn `145.8` into
  145.8 Hz without an error.

Affects: SPEC section 6, `entry.py`, `gui/log_tab.py`.

## D26. Folder fields reset for a new folder

Closes issue 14 of the Milestone 3 report.

- In the first build, the format fields kept their values when the user chose
  another folder. After `int8` was set for one folder, the next folder started on
  `int8`, and D21 filled in its fs for `int8`.
- When the folder of a new entry changes, these fields return to their defaults:
  file duration (1 s, then set from the file names again), sample type (`int16`),
  IQ layout (`interleaved_iq`), endianness (`little`), header bytes (0), the channel
  rows and the RF chain rows.
- Logged by, site, recording plan reference and remarks stay. The user decided the
  reset for the format, channel and RF chain sections only.
- Edit mode is unchanged: its folder cannot change (D16).

Affects: SPEC section 6, `gui/log_tab.py`.

## D27. Warning for a folder named like a channel folder

Closes issue 16 of the Milestone 3 report.

- In the second manual test, the folder chosen was `04_short_last_file\0`, a channel
  folder. The tab took it as a recording with relative path `0`.
- A new entry whose folder name has 1 to 3 digits without a leading zero, such as `0`
  or `12`, gets an information line that names the parent folder. A "Use parent
  folder" button switches to the parent.
- The warning does not block saving. The user decided that such a folder may be a
  real recording.
- Longer numbers, such as a Unix time like `1790733600`, do not trigger it. Channel
  indices are small, and recording folders named by Unix time would otherwise all
  get the warning.

Affects: SPEC section 6, `entry.py`, `gui/log_tab.py`.

## D28. RF chain repeats, overrides and conflicts

The user asked how the Log tab treats repeated and conflicting RF chain rows. Before
this decision it accepted any rows and saved them as typed.

- A Recording row is the value for every channel that has no row of its own.
- Rows compare by scope (Recording or one channel) and by name without letter case,
  as the schema's `COLLATE NOCASE` does. Values and units compare without letter case
  and without surrounding spaces.
- Same scope and same name with different values is an error, because nobody can tell
  which value is true. A different unit counts as a different value.
- Same scope, same name and same value is information. The row is saved once.
- A channel row with the same value as the Recording row is information ("repeats
  the Recording value"). It is saved as typed.
- A channel row with a different value from the Recording row is information: an
  override for that channel. It is saved as typed.
- A name already in the database is saved with its stored spelling. A new name takes
  the spelling of its first row in the form. The checklist names each changed
  spelling.
- A misspelt name, such as "Antena", is a separate parameter. The app does not try to
  catch spelling slips.

Affects: SPEC section 6, `entry.py`, `gui/log_tab.py`.

## D29. Settings tab before the Viewer

- The user decided on 2026-10-02 to build the settings as a fourth tab, "Settings",
  in place of the settings dialog that SPEC section 4 described for Milestone 7.
- The Settings tab is the next milestone, before Milestone 4 (Viewer).
- Reasons, from the Milestone 3 manual tests:
  - Every PC needs `db_path`. Today the user can set it only by editing
    `config.toml` by hand or with `--db`.
  - `nas_roots` decides whether a logged folder is local or archived (D14, D2).
  - Hand-edited Windows paths in TOML are easy to get wrong.
- The settings dialog and the config writer move out of Milestone 7. Milestone 7
  keeps the PyInstaller build, the legacy migration tool and the user guide.
- The scope is in SPEC section 4, "Settings tab". Its open questions are O18, O19 and
  O27–O31 in `docs/STATUS.md`. The milestone's working name is "Milestone 3a" (O27).

Affects: SPEC sections 1, 4, 9 and 12.

## D30. Settings scope: no upgrade button, fixed extensions, no database creation

Narrows D29. Closes O29. The user decided all three points on 2026-10-02 after
questions about the first scope.

- **No "Upgrade database" button in Milestone 3a.** No migration exists yet: the
  schema stays at version 1 until the first real database exists (D4). A button that
  cannot appear cannot be tested by hand. The status line shows the schema version.
  The button comes with the first real migration (O19). D6 is unchanged.
- **Data-file extensions are not a setting.** They stay fixed in code as `.dat` and
  `.bin`, in any letter case. `config.toml` is per machine, so a setting would let
  two PCs scan one folder differently. That would also affect the Viewer's gap scan
  and the transfer file lists. A new extension comes with a new release.
- **The app does not create databases from the GUI.**
  - The real shared catalogue comes once from the legacy migration tool
    (Milestone 7).
  - An empty database comes from `tools/db_check.py create` in development.
  - Milestone 7 packages the migration tool and adds an admin option,
    `--create-db PATH`, because the Python tools do not run on PCs without Python.
  - Reason: a "Create" button lets two people make two catalogues and log into
    different ones without noticing.
- **New open item O32.** The database does not store the file extension, and SPEC
  section 8 writes manifests as `<timestamp>.dat`. Transfers of `.bin` recordings
  need the real file names.

Affects: SPEC sections 4, 7, 8 and 12.

## D31. Writing config.toml with tomli-w

Closes O18. The user chose the proposed default on 2026-10-02.

- `config.save_config()` writes the file with `tomli-w`, a pure-Python package with no
  dependencies. It is pinned as `tomli-w==1.2.0` in `requirements.txt`.
- `tomli-w` writes every value that `tomllib` reads, so keys the tab does not show
  survive a Save, including nested tables and dates.
- It writes paths as basic strings with escaped backslashes, for example
  `"\\\\nas\\recordings"`. A hand-edited file may use literal strings
  (`'\\nas\recordings'`). Both read back the same.
- Before anything is written, the data is checked with `parse_config()`, and the
  TOML text is read back and compared.
- The text goes to `config.toml.new` in the same folder. The old file is copied to
  `config.toml.bak` (D35). `config.toml.new` then replaces `config.toml`. A failure
  before that last step leaves `config.toml` unchanged.
- Comments in the file are lost. The Settings tab says so.

Affects: SPEC section 4, `config.py`, `requirements.txt`, `pyproject.toml`.

## D32. Name of the Settings milestone

Closes O27. The user chose the proposed default on 2026-10-02.

- The Settings milestone is "Milestone 3a". Later milestones keep their numbers, so
  references such as "the Viewer in Milestone 4" stay true.

Affects: SPEC section 12, `docs/STATUS.md`.

## D33. Applying settings without a restart

Closes O28. The user chose the proposed default on 2026-10-02, with the refinement
below.

- Changes apply on Save. The app needs no restart.
- A new display offset redraws the times and column labels in the Log tab. The form
  keeps its input.
- A new `db_path` or new NAS roots clear the Log tab form and reload its lists. The
  folder location, the duplicate check and edit mode all depend on these two keys.
- Before such a Save, the app asks whether to clear the form if the form holds input
  that is not saved. Answering No writes nothing.
- "Input" means edit mode, or text in the folder, the plan reference, the remarks or
  an RF chain row.
- While the Log tab saves a recording, the Settings tab does not save. A message asks
  the user to save the settings when the recording is saved.
- With `--db`, the `--db` path stays in force after a Save. A change of `db_path` in
  the file then clears nothing.

Affects: SPEC section 4, `app.py`, `gui/log_tab.py`, `gui/settings_tab.py`.

## D34. Keys in the Settings tab

Closes O30. The user chose the proposed default on 2026-10-02.

- Milestone 3a shows the keys in use now: `db_path`, `nas_roots` and
  `display_utc_offset_hours` (`config.SETTINGS_KEYS`).
- Each later milestone adds its own keys to the tab: the coverage threshold
  (Milestone 4, O15); `default_local_copy_root`, `network_speed_mb_s`,
  `default_hash_mode`, `hash_sample_fraction` and a free-space margin (Milestones 5
  and 6).

Affects: SPEC section 4, `config.py`, `gui/settings_tab.py`.

## D35. Backup of config.toml

Closes O31. The user chose the proposed default on 2026-10-02.

- Each Save copies the existing file to `config.toml.bak` next to it. The copy
  replaces the backup of the Save before.
- The first Save, when no file exists, writes no backup.
- A file that cannot be read is also copied, so its text stays available.

Affects: SPEC section 4, `config.py`.

## D36. A wrong value in a key the Settings tab does not show

Found while planning Milestone 3a. The user chose the proposed rule on 2026-10-02.

- When a key that the tab does not show holds a wrong value, for example
  `network_speed_mb_s = -1`, Save stays disabled.
- The tab names the key and its rule. The user corrects the key in the file by hand
  ("Open folder"), then clicks "Reload from file".
- Reason: the app would otherwise write a file that it cannot read back.
- A wrong value in a key the tab shows is marked at its field and can be corrected
  there. A file that is not valid TOML can be replaced by Save (D35 keeps the old
  text).

Affects: SPEC section 4, `config.hidden_key_error()`, `gui/settings_tab.py`.

## D37. Status line for an older database

Found while planning Milestone 3a. The user chose the proposed text on 2026-10-02.

- SPEC section 4 said that the status line for `needs upgrade` names writes only. D6
  and `connection.connect()` refuse reads of an older database as well.
- The status line now reads "This version of the app cannot read or write this
  database."

Affects: SPEC section 4, `gui/settings_tab.py`.

## D38. Plain text for users; coloured database status

Replaces the wording of D37. The user decided on 2026-10-03, after the first look at
the Settings tab.

- **Principle.** Text in the app is for the people who log and move recordings. It
  must make sense without the planning documents. It names no decision numbers, open
  items, SPEC sections, config key names or database internals, and it does not
  explain design decisions. CLAUDE.md, "User-facing text", states the rules for
  agents. `tests/test_user_text.py` checks the Log and Settings tabs.
- **Database status colours.** The status line has a colour and a mark:
  - green ✓: the app can read and write the database ("Connected. The database is
    ready to use.");
  - amber ○ or ⓘ: no path yet, a check in progress, or a database from a newer app
    version, which the app can read only;
  - red ✗: the file is missing, is a folder, cannot be opened, is not an IQ Data
    Manager database, or comes from an older app version.
- **Technical detail in the tooltip.** The schema version, the version this app
  expects, the journal mode, foreign keys and busy timeout appear in the tooltip of
  the status line, for support. The visible line names none of them.
- **Older database.** The line reads "This database comes from an older version of
  IQ Data Manager. This version cannot open it." The meaning of D37 is unchanged:
  the app can neither read nor write it.
- **Other text in the Settings tab.** Labels drop the key names. "NAS roots" became
  "NAS locations". The note on displayed times and decision D24 is removed; the
  example line shows the effect. Error lines say what is wrong in plain words. The
  technical text of a settings-file error is in the tooltip.
- A wrong key that the tab does not show is still named, because the user corrects
  it by hand (D36).

Affects: CLAUDE.md, SPEC section 4, `gui/settings_tab.py`, `db/connection.py`,
`tests/test_user_text.py`.

## D39. Coverage highlight threshold

Closes O15. The user chose the proposed default on 2026-10-03.

- A new config key, `coverage_highlight_percent`, sets the threshold. The default is
  99. A value must be above 0 and at most 100.
- The Settings tab shows it in the Display group as "Highlight coverage below", from
  0.0 to 100.0 % with one decimal place. A value of 0 is marked as an error and
  blocks Save.
- The Viewer compares the coverage as shown, at one decimal place. A recording at
  98.95 % is shown as 99.0 % and is not marked at a threshold of 99.
- Coverage below the threshold is shown in amber with the ⓘ mark, in the recordings
  list and in the channels table. The tooltip names the threshold.
- Unknown coverage (no file count in the database) is shown as "unknown" and is not
  marked.

Affects: SPEC sections 4 and 5, `config.py`, `gui/settings_tab.py`, `viewer.py`,
`gui/widgets/recording_model.py`, `gui/viewer_tab.py`.

## D40. Recordings list at the size of the catalogue

Closes O16. The user expects fewer than 5,000 recordings in the catalogue for the next
few years (2026-10-03).

- `repository.list_recordings()` takes a `RecordingFilter` and filters in SQL.
  Channels are read only for the recordings that match.
- The recordings table is a `QTableView` over a model that sorts its own rows with
  `list.sort()`. A `QSortFilterProxyModel` called the model from Python for every
  comparison and blocked the main thread for about 0.5 s at 5,000 rows.
- Measured on a local disk with a synthetic catalogue (`dev/m4-bench/bench.py`):
  `list_recordings` took 53 ms for 5,000 recordings and 568 ms for 50,000. Showing
  5,000 rows took 41 ms, and sorting them 8 ms.
- No paging and no row limit. A catalogue far above 5,000 recordings would need them.

Affects: SPEC section 5, `db/repository.py`, `models.py`,
`gui/widgets/recording_model.py`.

## D41. No deletion of recordings in the GUI

Closes O17. The user chose the proposed default on 2026-10-03.

- The GUI has no action that deletes a recording from the catalogue in v1.
- A wrongly logged entry is corrected with "Edit entry". Removing an entry stays a
  manual database job. `repository.delete_recording()` exists and refuses a recording
  with transfer history.

Affects: SPEC sections 5 and 13.

## D42. No Copy / move button in the Viewer before Milestone 6

Found while planning Milestone 4. The user chose this on 2026-10-03.

- SPEC section 5 lists a "Copy / move" action that opens the Move / copy tab with the
  recording selected. That tab is a placeholder until Milestone 6.
- The Viewer has no Copy / move button until then. Milestone 6 adds the button
  together with the tab it opens.

Affects: SPEC sections 5 and 12.

## D43. Viewer filters

Found while planning Milestone 4. Part of the approved plan of 2026-10-03.

- The start date filters take `YYYY-MM-DD` and read the date at the display offset
  (D24). Their labels name the zone, for example "Start date from (UTC+8)". The "to"
  date includes its whole day. O1 covers time input in the Move / copy tab only.
- Band and the centre frequency range must match on the same channel. The range is
  in MHz and includes both ends.
- Text filters match a part of the text. "RF chain contains" matches a parameter's
  name, value or unit. `%` and `_` match literally. Letter case is ignored for ASCII
  letters only, as SQLite's `LIKE` does.
- Filters apply on Apply or Enter. A wrong value is marked under the filters, and no
  query runs.

Affects: SPEC section 5, `viewer.py`, `db/repository.py`, `gui/viewer_tab.py`.

## D44. The "not verified" mark in the Viewer

Found while planning Milestone 4. Part of the approved plan of 2026-10-03. Builds on
D2.

- An archived recording with the D2 row in `transfer_log` (`operation = 'check'`,
  `verification = 'skipped'`, `notes` = the in-place text) is shown as
  "archived, not verified" in amber. The details panel explains the mark.
- The mark stays while that row exists. How a later verification clears it is
  decided with O11 in Milestone 6.
- The in-place text moved from `entry.py` to `models.IN_PLACE_NOTE`, so the
  repository can use it.

Affects: SPEC section 5, `models.py`, `db/repository.py`, `viewer.py`.

## D45. Edit entry with unsaved input in the Log tab

Found while planning Milestone 4. Part of the approved plan of 2026-10-03.

- "Edit entry" in the Viewer switches to the Log tab and opens the recording in edit
  mode (D16).
- If the Log tab form holds input that is not saved (as in D33), the app asks first.
  "No" changes nothing and stays in the Viewer.
- While the Log tab saves a recording, the app shows a message and opens nothing.

Affects: SPEC section 5, `app.py`.

## D46. The Viewer refreshes after a Log tab save

Found while planning Milestone 4. Part of the approved plan of 2026-10-03.

- The Log tab emits `saved` with the recording id after a new or an edited entry is
  saved. The Viewer then queries the database again, with its filter and selection.
- Other changes to the database, for example from another PC, appear on Refresh.

Affects: SPEC section 5, `gui/log_tab.py`, `app.py`.

## D47. When a recording last changed

The user asked after the Milestone 4 manual tests whether edits should be tracked, and
chose the smallest option on 2026-10-03.

- The schema already stores `recordings.updated_at`. A trigger sets it on every
  update of the row. The Viewer did not show it.
- The Viewer's details panel now reads, for example, "by userA on 2026-10-01 08:00;
  last changed on 2026-10-02 11:30". The last change is left out when `updated_at`
  equals `created_at`.
- A Save in edit mode whose values equal the stored ones writes nothing, and the Log
  tab says "No changes to save." Before this, such a Save rewrote the row and moved
  `updated_at`. Parameters compare as a set, as `update_recording()` stores them (D7).
- The time means "last changed". From Milestone 6, archiving to the NAS also changes
  the row and moves the time.
- Who made the change is not recorded. The user decided against an `updated_by`
  column and against an edit history.

Affects: SPEC sections 5 and 6, `entry.py`, `gui/log_tab.py`, `gui/viewer_tab.py`.
