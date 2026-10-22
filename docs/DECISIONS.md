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
| D4 | Schema baseline | 2026-10-02, Milestone 1 | Active; D77 ends the edits in place |
| D5 | Transfer log columns | 2026-10-02, Milestone 1 | Active; D52 adds the deletion record |
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
| D19 | Band and frequency input | 2026-10-02, Milestone 3 | Active; fs input replaced by D25; D88 fills the band from fc |
| D20 | RF chain rows of channels removed by a rescan | 2026-10-02, Milestone 3 | Active |
| D21 | fs from the file size | 2026-10-02, Milestone 3 | Active |
| D22 | File duration from the file names; coverage above 100 % | 2026-10-02, Milestone 3 | Active |
| D23 | To-do items in the checklist | 2026-10-02, Milestone 3 | Active |
| D24 | Display offset for times | 2026-10-02, Milestone 3 | Active |
| D25 | fs input with units | 2026-10-02, Milestone 3 | Active |
| D26 | Folder fields reset for a new folder | 2026-10-02, Milestone 3 | Replaced by D79 |
| D27 | Warning for a folder named like a channel folder | 2026-10-02, Milestone 3 | Active |
| D28 | RF chain repeats, overrides and conflicts | 2026-10-02, Milestone 3 | Active |
| D29 | Settings tab before the Viewer | 2026-10-02, after Milestone 3 | Active; scope narrowed by D30 |
| D30 | Settings scope: no upgrade button, fixed extensions, no database creation | 2026-10-02, after Milestone 3 | Active; D67 replaces its point on database creation |
| D31 | Writing config.toml with tomli-w | 2026-10-02, Milestone 3a | Active |
| D32 | Name of the Settings milestone | 2026-10-02, Milestone 3a | Active |
| D33 | Applying settings without a restart | 2026-10-02, Milestone 3a | Active |
| D34 | Keys in the Settings tab | 2026-10-02, Milestone 3a | Active; D39 added the coverage threshold |
| D35 | Backup of config.toml | 2026-10-02, Milestone 3a | Active |
| D36 | A wrong value in a key the Settings tab does not show | 2026-10-02, Milestone 3a | Active |
| D37 | Status line for an older database | 2026-10-02, Milestone 3a | Replaced by D38 |
| D38 | Plain text for users; coloured database status | 2026-10-03, Milestone 3a | Active |
| D39 | Coverage highlight threshold | 2026-10-03, Milestone 4 | Active |
| D40 | Recordings list at the size of the catalogue | 2026-10-03, Milestone 4 | Active |
| D41 | No deletion of recordings in the GUI | 2026-10-03, Milestone 4 | Replaced by D89 |
| D42 | No Copy / move button in the Viewer before Milestone 6 | 2026-10-03, Milestone 4 | Active |
| D43 | Viewer filters | 2026-10-03, Milestone 4 | Active; D78 allows several sites, projects and bands |
| D44 | The "not verified" mark in the Viewer | 2026-10-03, Milestone 4 | Active |
| D45 | Edit entry with unsaved input in the Log tab | 2026-10-03, Milestone 4 | Active |
| D46 | The Viewer refreshes after a Log tab save | 2026-10-03, Milestone 4 | Active |
| D47 | When a recording last changed | 2026-10-03, Milestone 4 | Active |
| D48 | The app copies files itself | 2026-10-03, Milestone 5 | Active; D54 moves the NAS measurement |
| D49 | Files in a time range | 2026-10-03, Milestone 5 | Active |
| D50 | Archiving needs the whole recording | 2026-10-03, Milestone 5 | Active |
| D51 | Destination folders and resuming | 2026-10-03, Milestone 5 | Active |
| D52 | Deletion record and transfer manifest | 2026-10-03, Milestone 5 | Active |
| D53 | File names come from a rescan | 2026-10-03, Milestone 5 | Active |
| D54 | NAS field test with the Milestone 6 build | 2026-10-03, Milestone 5 | Active |
| D55 | Deleting the laptop copy after a check past the cache | 2026-10-03, Milestone 6 | Active; D74 compares the order of the rows |
| D56 | Compare with laptop copy | 2026-10-03, Milestone 6 | Active |
| D57 | Diagnostics in a console companion program | 2026-10-03, Milestone 6 | Active |
| D58 | Files copied at once as a setting | 2026-10-03, Milestone 6 | Active |
| D59 | Time input at the display offset | 2026-10-03, Milestone 6 | Active |
| D60 | Destination of a copy to a PC | 2026-10-03, Milestone 6 | Active |
| D61 | One capture logged twice | 2026-10-03, Milestone 6 | Active |
| D62 | Transfer notes are appended | 2026-10-03, Milestone 6 | Active |
| D63 | Skipped files are hashed | 2026-10-03, Milestone 6 | Active |
| D64 | "Archive" in place of "move" | 2026-10-03, Milestone 6 | Active |
| D65 | Long paths in the packaged app | 2026-10-04, Milestone 7 | Active |
| D66 | Legacy import | 2026-10-04, Milestone 7 | Active |
| D67 | New database in the Settings tab | 2026-10-04, Milestone 7 | Active |
| D68 | Defaults file in the program folder | 2026-10-04, Milestone 7 | Active |
| D69 | Information notes in the Settings tab | 2026-10-04, Milestone 7 | Active |
| D70 | Unsaved settings | 2026-10-04, Milestone 7 | Active |
| D71 | Legacy dates and times from the folder | 2026-10-06, Milestone 7 | Active |
| D72 | Milestone 8: release 1.0 | 2026-10-06, end of Milestone 7 | Active |
| D73 | A project for each recording | 2026-10-11, Milestone 8 | Active; D78 replaces its Viewer filter |
| D74 | Transfer rows in the order they were written | 2026-10-11, Milestone 8 | Active |
| D75 | File identity in the transfer checks | 2026-10-11, Milestone 8 | Active |
| D76 | An edit saves only over the entry it opened | 2026-10-11, Milestone 8 | Active |
| D77 | Version 1 schema frozen | 2026-10-20, after 1.0.0 | Active |
| D78 | Viewer filters with several choices | 2026-10-20, version 1.1 | Active |
| D79 | A new folder keeps the previous entry's fields | 2026-10-20, version 1.1 | Active |
| D80 | Log tab templates in files | 2026-10-20, version 1.1 | Active |
| D81 | A queue in the Archive / copy tab | 2026-10-20, version 1.1 | Active; D85 adds a state |
| D82 | Values from the recorder's log | 2026-10-21, version 1.1 | Active |
| D83 | The recorder's log files travel with the recording | 2026-10-21, version 1.1 | Active |
| D84 | The Log tab's message line shows its state | 2026-10-22, version 1.1 | Active |
| D85 | An archive whose check is still needed | 2026-10-22, version 1.1 | Active; amends D81 |
| D86 | A paused queue item continues in the queue only | 2026-10-22, version 1.1.1 | Active; amends D81 |
| D87 | A template imported after the log filled the form | 2026-10-22, version 1.1.1 | Active; amends D80 and D82 |
| D88 | The band filled in from fc | 2026-10-23, version 1.2 | Active; amends D19 |
| D89 | Deleting an entry added by mistake | 2026-10-23, version 1.2 | Active; replaces D41 |
| D90 | Logging several folders with one set-up | 2026-10-23, version 1.2 | Active |

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
  Milestone 5. D52 adds both.

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
- **Replaced by D89** (2026-10-23): the Log tab's edit mode deletes an entry that has
  no archive, copy or delete in its history.

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

## D48. The app copies files itself

Closes O13. The user chose this on 2026-10-03, while planning Milestone 5, after the
agent compared four approaches: scripts the user runs, scripts the app runs, a copy
engine in the app, and the engine with a script export.

- The app copies files with its own Python copy engine, `transfer/copier.py`, in a
  worker thread. It generates no robocopy or PowerShell scripts in v1. `scripts/` and
  `runner.py` leave the SPEC layout.
- Reasons:
  - Agents may not run robocopy or generated scripts. With scripts, the first real
    run of the copy, verify and delete chain would have been the user's manual test.
    The engine runs in the tests on synthetic recordings under `tmp_path`.
  - Robocopy has no option that reads a list of relative paths, so a time range or a
    channel subset needed a second mechanism in PowerShell.
  - Windows 10 and 11 clients do not run PowerShell scripts by default.
  - Progress from robocopy comes from its text output. Its exit codes 1 to 7 also
    mean success.
  - A script the user runs alone leaves the app without a start time, an end time or
    a result.
  - The engine needs no rsync generator for Linux.
- The engine copies each file to `<name>.partial`, keeps the source's modification
  time, and renames the file to its real name only when it is complete. The rename
  never replaces an existing file. A file under its real name is therefore always
  complete.
- Each file gets up to 3 retries after the first attempt, with 5 s between them, as
  robocopy's `/R:3 /W:5` did. Progress counts files and bytes. Cancel stops between
  chunks and leaves the `.partial` file in place.
- The engine can hash the source while it reads it, and can copy several files at
  once. The number of files at once is a parameter; O35 proposes a setting.
- Throughput on the NAS is not measured yet. `tools/copy_check.py` measures it. D54
  moved that measurement to the NAS field test with the Milestone 6 build.
- A copy made by hand outside the app is still covered by "Check archive".
- The safety rules for agents in CLAUDE.md are unchanged.

Affects: SPEC sections 1, 8, 9, 11 and 12, CLAUDE.md, `transfer/copier.py`,
`tools/copy_check.py`.

## D49. Files in a time range

Closes O6. The user chose the proposed default on 2026-10-03.

- A file with timestamp `t` belongs to the range from `start` to `end` when
  `start <= t < end`. The end is exclusive, as `end_unix` is everywhere else.
- The missing seconds of a range are the gap seconds (D12) that fall inside the range.
  Time before a channel's first file or after its last file is not counted as missing.

Affects: SPEC section 8, `transfer/selection.py`.

## D50. Archiving needs the whole recording

Closes O7. The user chose the proposed default on 2026-10-03.

- "Archive to NAS" moves only a whole recording with all its channels. A time range or
  a channel subset would point the database at a partial copy.
- The recording must be `local`.
- The folder must match the database entry: the same channels, and the same file
  count and total size per channel where the database holds them. Otherwise the
  stored counts would not describe the archived copy. The user rescans the folder in
  the Log tab first.
- The destination must lie under a configured NAS root. Its `storage_root` and
  `rel_path` follow D14, and no other recording may use that location.

Affects: SPEC section 8, `transfer/operations.py`, `transfer/pathcheck.py`.

## D51. Destination folders and resuming

Closes O8. The user chose this on 2026-10-03: the proposed default, with resuming.

- The target files are the selection's files under their relative paths in the
  destination folder.
- A move needs a destination that is new, is empty, or holds only target files,
  their `.partial` files and their channel folders. The last case is an interrupted
  move of the same selection, which the engine resumes.
- A copy also accepts a destination that holds other files.
- A target file that already exists with the source file's size counts as copied.
  The engine skips it, and verification checks it like every other file.
- A target file that exists with another size makes the destination check refuse the
  transfer, before anything is written. If such a file appears after the check, the
  engine leaves it alone and the transfer is logged as failed. The engine never
  replaces it.
- A free-space margin is kept on the destination. A new key, `free_space_margin_gb`
  (default 10), sets it. Milestone 5 reads the key; the Settings tab shows it from
  Milestone 6 (D34).

Affects: SPEC sections 4 and 8, `config.py`, `transfer/pathcheck.py`,
`transfer/copier.py`.

## D52. Deletion record and transfer manifest

Closes O9 and the deferred part of D5. The user chose this on 2026-10-03.

- `transfer_log` gets three columns: `parent_id`, `manifest_path` and
  `manifest_sha256`. `operation` also accepts `'delete'`. `schema.sql` is edited in
  place (D4).
- A deletion of the laptop copy is a `transfer_log` row with `operation = 'delete'`.
  Its `parent_id` is the move it follows. A trigger refuses the row unless the parent
  is a move of the same recording with `verification = 'pass'`. `parent_id` is set
  exactly for delete rows.
- A delete row's `verification` is `'pass'` when every listed file was deleted and
  `'fail'` when any remained. `notes` names what remained.
- After each copy or move that passes verification, the app writes a manifest: a
  JSON file in a `manifests` folder next to the configuration file, normally
  `%APPDATA%\IQDataManager\manifests\transfer-<id>-<time>.json`, for example
  `transfer-7-20261003T080000Z.json`. The time is the finish time. It keeps two
  manifests apart when two databases on one PC reuse a transfer id, for example a
  test catalogue and the real one. The manifest lists each file's relative path,
  size and SHA-256 where one was computed. The app writes it only to a new file.
  `manifest_path` holds its path, and `manifest_sha256` the SHA-256 of its bytes.
- A move's destination is stored as its NAS location (D14), with a mapped drive
  letter replaced by the UNC path. The log row, the manifest and the recording
  therefore name the same folder.
- `transfer/delete.py` deletes source files only when all of these hold:
  - the move row has `verification = 'pass'` and a manifest;
  - the manifest's SHA-256 matches `manifest_sha256`;
  - the recording now points at the move's destination;
  - each destination file still has its manifest size, checked right before its
    source file is deleted;
  - each source file still has its manifest size.
- It deletes only the files in the manifest. Afterwards it removes channel folders
  and the recording folder only when they are empty. It refuses relative paths with
  `..`, absolute paths and links.

Affects: SPEC sections 3 and 8, `schema.sql`, `models.py`, `db/repository.py`,
`viewer.py`, `transfer/manifest.py`, `transfer/delete.py`.

## D53. File names come from a rescan

Closes O32. The user chose this on 2026-10-03 in place of the proposed default
(storing the extension).

- Before every transfer the app rescans the source folder with the scanner. The
  rescan gives the real file names, including `.dat` or `.bin`, each file's size and
  the gaps inside the range.
- The preview needs per-file sizes and the gaps of the range in any case, and the
  database stores neither. A rescan also handles a channel that holds both
  extensions, which the scanner allows (D11).
- The schema stores no file extension.

Affects: SPEC section 8, `transfer/selection.py`.

## D54. NAS field test with the Milestone 6 build

The user decided on 2026-10-03, after the Milestone 5 report. Development happens away
from the network that holds the NAS. A test there means taking a frozen build to a
recording laptop and reporting back the next day.

- The copy engine is not tested on the NAS before Milestone 6. The first NAS test
  uses the Milestone 6 build, with the Move / copy tab.
- `tools/make_nas_testset.py` writes the data for that test on the laptop: five
  synthetic recordings of random bytes (large files, many small files, gaps and
  ranges, a single `.bin` channel with a short last file, half-second files), with
  `TESTSET.md` and `testset.json`. The default set holds 5.05 GB.
- `tools/copy_check.py` measures throughput with 1, 4 and 8 files at once, with the
  flush to the destination's disks on and off (`--fsync both`), on a test-set
  recording (`--source`).
- `copy_files()` takes `fsync=False` for that comparison only. The app keeps the
  flush. The flush ensures that a crash on the NAS cannot leave a file with its real
  name and size but without its data, which a size check would pass.
- Risks the user accepted:
  - throughput to the NAS, above all for many small files, is unknown until then;
  - a check straight after a copy may read from the PC's cache;
  - engine faults and tab faults turn up in the same trip.
- The Milestone 6 plan takes up three open items that reduce these risks: O34
  (diagnostics and the test set in the packaged app), O35 (files at once and the
  flush as settings) and O36 (deletion only after a later check).

Affects: SPEC sections 8, 9 and 12, `transfer/copier.py`, `tools/copy_check.py`,
`tools/make_nas_testset.py`, `tools/make_fixtures.py`.

## D55. Deleting the laptop copy after a check past the cache

Closes O36. The user chose this on 2026-10-03, while planning Milestone 6.

- A check straight after a copy to the NAS may read the files from the PC's file
  cache (Milestone 5 report, "Untested"). Its hashes may then compare the PC's memory
  with the source.
- The proposed default was a later "Check archive". That check scans directory
  entries and reads no file contents, so it cannot find such a problem. A restart of
  the app does not empty the Windows file cache, which belongs to the system.
- A separate action, "Check before delete", reads the NAS files of a passed archive
  with the Windows file cache bypassed (`FILE_FLAG_NO_BUFFERING`). It hashes them in
  the chosen hash mode. Each hash is compared with the copy-time hash in the
  manifest, or with a hash of the laptop file where the manifest holds none.
- Hash mode `none` is refused for this check. In that mode the sizes come from the
  directory entries and no file content is read. Found in self-review
  (`95c9256`).
- The check is logged as a `check` row whose `parent_id` names the archive.
  `schema.sql` is edited in place (D4).
- `delete.py` refuses to delete unless such a check passed after the archive
  finished. A passed check stays valid for a later delete run of the same archive.
  The per-file size checks of D52 still run right before each file.
- D74 replaced the time comparison of the point above: the check's row must be
  written after the archive's row.
- The NAS field test (D54) confirms that the bypass reads from the NAS.

Affects: SPEC sections 3 and 8, `schema.sql`, `transfer/verify.py`,
`transfer/delete.py`, `transfer/operations.py`.

## D56. Compare with laptop copy

Closes O11. The user chose the proposed option on 2026-10-03.

- An archived recording with the "not verified" mark (D2, D44) gets an action,
  "Compare with laptop copy". The user picks the laptop folder.
- The app compares the channels, the file count and each file's size between the
  laptop folder and the NAS folder, with SHA-256 in the chosen hash mode.
- The comparison is logged as a `check` row with the laptop folder as `source`, the
  NAS folder as `destination` and the hash mode.
- The mark is shown while the in-place row exists and no later comparison row
  passed. No row is removed.
- A passed comparison does not allow deleting the laptop copy. Deletion stays tied to
  a passed archive and its manifest (D52, D55).

Affects: SPEC sections 5 and 8, `viewer.py`, `db/repository.py`,
`transfer/operations.py`.

## D57. Diagnostics in a console companion program

Closes O34. The user chose this on 2026-10-03 in place of the proposed default
(options of the main program).

- The packaged app is windowed (D8). It has no console, so text that a command-line
  option prints would not appear.
- The build folder holds a second program, `IQDataManager-check.exe`, which runs in a
  console. Its subcommands are `copy-check`, `db-check` and `make-test-set`, with the
  options of the tools in `tools/`.
- The code moves from `tools/` into `src/iqdm/diagnostics/`. The scripts in `tools/`
  stay as thin wrappers, so the commands in the reports keep working.
- `db-check` refuses `check`, `write` and `hold` on a database that holds any
  recording other than its own test rows. On a laptop whose settings point at the
  real catalogue, it then writes nothing there.

Affects: SPEC sections 9, 11 and 12, `build/iqdm.spec`, `tools/`.

## D58. Files copied at once as a setting

Closes O35. The user chose the proposed default on 2026-10-03.

- A new key, `copy_workers`, sets the number of files copied at once. The default is
  4, and a value runs from 1 to 16. The Settings tab shows it as "Files copied at
  once".
- The flush to the destination's disks stays on and is not a setting. Deletion relies
  on it (D54). `copy-check` still measures with the flush on and off.

Affects: SPEC sections 4 and 8, `config.py`, `gui/settings_tab.py`.

## D59. Time input at the display offset

Closes O1. The user chose this on 2026-10-03 in place of the proposed default (UTC).

- The "From" and "To" fields of a time range read a date and time at the display
  offset (D24). Their labels name the zone, for example "From (UTC+8)".
- Fields in Unix seconds sit next to them. Each pair is kept in sync.
- Reason: the timeline axis, the Viewer's date filters (D43) and every other time on
  screen use the display offset.

Affects: SPEC section 8, the Archive / copy tab.

## D60. Destination of a copy to a PC

Closes O10. The user chose the proposed option on 2026-10-03.

- For a copy to a PC, the destination field is filled in with
  `default_local_copy_root` and the recording's relative path, for example
  `D:\work\iq\2026\LocationA\20260918_0300`. The NAS folder structure is kept.
- The user can edit the path or use Browse. Without `default_local_copy_root` the field
  starts empty.

Affects: SPEC section 8, the Archive / copy tab.

## D61. One capture logged twice

Closes O25. The user chose the proposed option on 2026-10-03.

- A recording copied to the NAS by hand and logged there (D2) can also be logged from
  its laptop folder. The two locations differ, so `UNIQUE (storage_root, rel_path)`
  accepts both.
- When another recording has the same start, end and channel indices, the Log tab
  checklist shows an information line that names it.
- The archive preview shows a warning when such a recording is archived.
- Neither blocks.

Affects: SPEC sections 6 and 8, `entry.py`, `db/repository.py`,
`transfer/operations.py`.

## D62. Transfer notes are appended

Closes O12. The user chose the proposed default on 2026-10-03.

- `repository.finish_transfer()` adds a new note after the text already stored,
  separated by a space. Before this decision a new note replaced the stored text.
- A note of None keeps the stored text.

Affects: `db/repository.py`.

## D63. Skipped files are hashed

Closes issue 4 of the Milestone 5 report. The user decided on 2026-10-03, after
asking how a stopped copy resumes.

- A target file already in place with the source's size is skipped by the copy
  (D51). Before this decision, verification trusted it by its size unless the hash
  mode chose it.
- When the hash mode is not `none`, verification now hashes every skipped file, on
  the source and in the destination. With `none` it compares sizes only.
- Reason: a file of the right size may come from outside the app, for example from a
  hand copy (D2). A Windows copy that stopped part-way may leave a file at its full
  size.
- Cost: a resumed run reads the files already copied again, on both sides. The
  preview's time estimate includes that reading.

Affects: SPEC section 8, `transfer/verify.py`, `transfer/estimate.py`,
`transfer/operations.py`.

## D64. "Archive" in place of "move"

The user decided on 2026-10-03, while planning Milestone 6.

- The operation called "move" never moved files. It copies the recording to the NAS,
  verifies the copy, and points the recording at it. The laptop copy stays until the
  separate, confirmed delete (D52). The word "move" suggested that files leave the
  laptop.
- The app uses three terms: **copy** (to a PC; the recording entry is unchanged),
  **archive** (to the NAS; the recording then points at the NAS copy) and **delete**
  (the laptop copy, after a passed archive).
- The change covers the code and the database: `Operation.ARCHIVE`, stored as
  `'archive'`, the `operation` CHECK constraint and the delete triggers
  (`schema.sql` edited in place, D4), `repository.finish_archive()` and
  `operations.delete_laptop_copy(archive_id)`.
- The tab is "Archive / copy", and the Viewer's button has the same name. SPEC,
  STATUS and CLAUDE.md use the new terms. The user approved the CLAUDE.md change.
- Entries D1 to D54 keep their wording. In them, "move" means an archive.
- A database made before this change refuses archive rows. Scratch databases are made
  again with `tools/db_check.py create`.

Affects: CLAUDE.md, SPEC sections 1, 3, 5, 8, 9 and 12, `schema.sql`, `models.py`,
`db/repository.py`, `transfer/`, `viewer.py`, `entry.py`, `app.py`.

## D65. Long paths in the packaged app

Closes O33. Found while planning Milestone 7, in the plan the user approved on
2026-10-04.

- PyInstaller 6.22.3 writes a manifest into each executable, and that manifest
  declares `longPathAware` as true. Both programs in `dist/m6-3` hold
  `<longPathAware ...>true</longPathAware>`.
- The packaged app therefore uses paths above the Windows limits on a PC where long
  paths are enabled in the registry (`LongPathsEnabled`). `transfer/pathcheck.py`
  already reads that setting.
- `build/iqdm.spec` sets no manifest of its own. A build check finds the declaration
  in both executables (README, "Build").
- The user guide explains the registry setting.

Affects: README.md, `docs/USER_GUIDE.md`.

## D66. Legacy import

Settles the details of SPEC section 10. The user described the legacy columns on
2026-10-04 and approved the plan.

- The legacy table has the columns `date`, `date_unix`, `site`, `band`, `fc_hz`,
  `fs_hz`, `duration_s`, `data_dir` and `remarks`.
  - `date` is text at UTC+8. `date_unix` is Unix seconds, and it always wins over
    `date`.
  - `fc_hz` and `fs_hz` are in Hz. `duration_s` is whole seconds.
  - Each channel of a multi-channel capture is a separate row. Its `data_dir` ends in
    the channel folder, for example `\\192.168.1.50\Data\IQ\recording1\0\` and
    `\\192.168.1.50\Data\IQ\recording1\1\`.
  - All legacy recordings are on the NAS. All are `int16`, interleaved I then Q, with
    no header.
- The import opens a copy of the legacy file read-only and writes a new database. It
  refuses an output file that exists and the legacy file itself as output.
- Folder rules:
  - A trailing separator is removed. A mapped drive letter is replaced by the UNC
    path given with `--drive`. The import makes no network call for this.
  - A last folder whose name is a canonical decimal number (D11) is a channel folder.
    It gives `channel_index` and `sub_path`, and its parent is the recording folder.
    Any other folder is the recording folder, with channel 0 and an empty `sub_path`.
  - The recording folder splits into `storage_root` and `rel_path` by D14, under the
    NAS roots given with `--nas-root`. A folder outside every NAS root, a NAS root
    itself and a share root cannot be mapped.
- Rows with the same recording folder, compared without letter case, form one
  recording. A group cannot be mapped in three cases:
  - a channel index appears twice;
  - the group mixes channel folders with the bare recording folder;
  - its rows name different sites, compared without letter case.
- Different remarks within one group are joined with " | ".
- Each row gives one channel: `fc_hz`, `fs_hz` above 0, `start_unix = date_unix` and
  `end_unix = date_unix + duration_s`. An empty band gives NULL. `n_files` and
  `total_bytes` stay NULL until a Check archive fills them in.
- `date` is read as UTC+8 and compared with `date_unix`. A difference above 1 s, or a
  `date` that cannot be read, gives a warning. The import uses `date_unix`.
- There is one site per name, compared without letter case. The first spelling in row
  order is kept.
- Each recording gets `logged_by = 'legacy-import'`, `archive_state = 'archived'`,
  `archived_at` = the import time, `int16`, `interleaved_iq`, little-endian, no header
  and `file_duration_s = 1.0`.
- Each recording also gets the D2 row, so the Viewer shows "archived, not verified".
  The user runs Check archive or Compare with laptop copy (D56) afterwards.
- Rows that cannot be mapped go to a report, with the warnings. The import guesses
  nothing. The report is printed, and a real run also writes it next to the new
  database as `<new database>.report.txt`. A dry run writes nothing.
- All recordings are written in one transaction. If it fails, the new file stays with
  the empty schema, and the message names it.
- The command is `IQDataManager-check.exe migrate-legacy` (D57). The same code runs as
  `tools/migrate_legacy.py`.
- Known limit: a legacy recording with files shorter than 1 s keeps
  `file_duration_s = 1.0`. Check archive does not change that value.

Affects: SPEC sections 9, 10 and 12, `legacy.py`, `db/legacy.py`, `check_main.py`,
`tools/migrate_legacy.py`.

## D67. New database in the Settings tab

Replaces the D30 point "The app does not create databases from the GUI", with its
admin option `--create-db PATH`. The user chose this on 2026-10-04.

- Some users want a private database for a project. Most users do not use a console,
  so a command-line option or a console command would not serve them.
- The Settings tab's Database section gets a "New database..." button. It opens a
  save dialog for a new `.db` file. A file that exists is refused.
- A Yes/No dialog asks first and defaults to No. It says that the new database is
  empty and separate from the shared catalogue, and that its recordings do not appear
  in the shared catalogue.
- The app creates the database from `schema.sql` with `connection.create_database()`,
  in a worker thread. The path then goes into "Database file", and the status check
  runs. Save switches the app to the new database, as after Browse.
- The status bar names the database in use, so a user sees which catalogue receives
  a new recording.
- The shared catalogue comes only from the legacy import (D66). `db-check create`
  stays for development and the field test.
- The other points of D30 stand.

Affects: SPEC sections 4 and 12, `gui/settings_tab.py`.

## D68. Defaults file in the program folder

The user chose this on 2026-10-04.

- Each PC keeps its own settings file, `%APPDATA%\IQDataManager\config.toml`. Without
  one, the app has no database and no NAS roots, and each user has to enter both.
- The packaged app looks for `defaults.toml` in the folder of `IQDataManager.exe`.
  While the settings file in use does not exist, the app reads its settings from
  `defaults.toml`. The settings file in use is `config.toml`, or the file given with
  `--config`.
- The Settings tab shows those values and names the defaults file. Save writes them,
  with any change, to the settings file. From then on that PC ignores the defaults
  file. A later change to `defaults.toml` does not reach a PC that has a settings
  file.
- The defaults file has the format and rules of `config.toml`. A wrong value in it is
  shown in the same way as a wrong value in `config.toml`.
- The app never writes `defaults.toml`. The app run from source has no defaults file.
- The build folder holds `defaults.example.toml` with example values. Whoever prepares
  the build for the team fills it in and saves it as `defaults.toml`. The repository
  holds no real path.

Affects: SPEC sections 4 and 9, `config.py`, `app.py`, `gui/settings_tab.py`,
`build/iqdm.spec`, `build/defaults.example.toml`.

## D69. Information notes in the Settings tab

The user asked for this on 2026-10-04, after the Milestone 7 build check.

- Three notes in the Settings tab tell the user that the values in use do not come
  from the settings file alone:
  - the values come from the defaults file (D68);
  - the app was started with `--config` or `--db` (About section);
  - the app was started with `--db` (under "Database file").
- They were plain text and easy to miss. Each is now amber with the ⓘ mark, in the
  checklist colours for the light or dark theme (D38). The mark keeps the meaning
  when the colour cannot be seen.
- The note about `config.toml.bak` above Save stays plain.

Affects: SPEC section 4, `gui/settings_tab.py`.

## D70. Unsaved settings

The user asked for this on 2026-10-04, after the Milestone 7 build check.

- Changes in the Settings tab apply only on Save (D33). A user who left the tab
  without saving had no sign that the changes were not written.
- While the fields differ from the file, the tab's title is "Settings (not saved)".
- Leaving the tab with unsaved changes asks first, with three buttons:
  - **Save** saves and moves on. If the save fails or is cancelled, the Settings tab
    stays open.
  - **Leave without saving** reads the file again, so the fields show the saved
    values, and moves on.
  - **Stay** keeps the Settings tab open with the changes.
- When a field holds a wrong value, Save cannot run. The question then says so and
  offers only "Leave without saving" and "Stay".
- Closing the window with unsaved settings asks the same question, with "Close
  without saving" in place of "Leave without saving". It comes before the question
  about a running operation.

Affects: SPEC section 4, `app.py`, `gui/settings_tab.py`.

## D71. Legacy dates and times from the folder

Amends D66. The user reported on 2026-10-06, after the legacy dry run on real data,
and chose the approach.

- The legacy `date` holds a day only, such as `12-Apr-2023`. `date_unix` follows it,
  so it gives the day and not the time of the first file. The dry run warned on
  every row, because the import could not read that form.
- The import reads `12-Apr-2023` and `12-Apr-2023 11:00:00`, besides the ISO 8601
  forms. For a text with a day only, it warns when `date_unix`, read at UTC+8, falls
  on another day. A text with a time keeps the 1 s rule of D66.
- The real times come from the files. Check archive scans the folder already. For a
  channel without stored counts, it now also takes the start from the first file and
  the end from the last file plus the file duration. The recording's date, start and
  end are derived again from its channels (D7). Only the legacy import leaves
  channels without counts; the Log tab always stores them.
- When the files' median spacing differs from the stored file duration by more than
  1 % (D22), the check's note says so. The value is not changed; the user corrects it
  in the Log tab's edit mode.
- Entries with counts are checked as before. Their times are neither compared nor
  changed.
- The user runs Check archive once on each imported recording, about 40. The "not
  verified" mark stays, because no source was compared (D56).

Affects: SPEC sections 8 and 10, `legacy.py`, `transfer/operations.py`,
`db/repository.py`, `models.py`.

## D72. Milestone 8: release 1.0

The user decided on 2026-10-06, at the end of Milestone 7, after asking whether the
app was ready for a first version.

- Milestone 7 closes with its packaging and migration work. The checks that need the
  NAS and the steps that create the real catalogue form a new milestone, Milestone 8,
  "Release 1.0".
- Before the real catalogue is used, these must pass:
  - O21, locking between two PCs on a scratch database on the NAS;
  - D55, Check before delete reads past the PC's file cache, shown by the Windows
    counter of received bytes (`netstat -e`), because on 10 GbE a time cannot tell;
  - the legacy import of a copy of the real legacy database, and Check archive on
    each imported recording, in a trial catalogue that the user reviews;
  - O20, the version 1 schema frozen when the real catalogue is created (D4);
  - version 1.0.0 in place of 0.1.0, a final build from `main` and release notes.
- Recommended before rollout: O22 (a backup of the catalogue outside the app), a
  pilot that archives one real recording and deletes its laptop copy while the user
  watches, and `defaults.toml` filled with the real paths and the measured copy
  settings (D68).
- Not needed for version 1: O37 (small-file speed), a batch Check archive, and code
  signing.

Affects: SPEC section 12, `docs/STATUS.md`.

## D73. A project for each recording

The user asked for this on 2026-10-11, after the second visit to the NAS, and chose
each point.

- Each recording can belong to one project, so people can filter for the data of
  their project. The project is optional.
- Projects are a list like sites: a `projects` table with names unique without letter
  case. The Log tab offers a dropdown of the projects in the database, an empty
  choice, and "Add project". The app has no rename or delete for projects, as for
  sites (D7).
- `recordings.project_id` refers to `projects` and may be NULL.
- The Log tab saves and edits the project like the site; a change needs no rescan.
- The Viewer shows a Project column after Site, a Project filter (all projects, no
  project, or one project) and the project in the details panel. The Archive / copy
  tab shows the project in the recording line.
- The legacy import leaves the project empty. Projects of legacy recordings are set
  afterwards with Edit entry.
- `schema.sql` is edited in place at version 1, because the real catalogue does not
  exist yet (D4). The change must come before the real catalogue and O20.
- A database made before this change has version 1 too, so its version number cannot
  tell it apart. The database check now compares the file with `schema.sql`: a file
  at the current version that lacks a table or column of `schema.sql` counts as an
  older version. The Settings tab shows it in red, and the app refuses to read or
  write it. Scratch databases made before this change are made again.

Affects: SPEC sections 3, 5, 6 and 8, `schema.sql`, `db/version.py`, `models.py`,
`db/repository.py`, `entry.py`, `viewer.py`, `gui/log_tab.py`, `gui/viewer_tab.py`,
`gui/transfer_tab.py`.

## D74. Transfer rows in the order they were written

Found on 2026-10-11 in the logs of the second visit: one PC's clock was about 50 s
behind the other's. The user approved the fix.

- Each PC writes times from its own clock. Three places compared or sorted times
  that different PCs wrote:
  - a delete needed a check before delete that started after the archive finished
    (D55). A check on a slower PC within a minute of an archive would have been
    refused as missing;
  - the transfer history of a recording, sorted by start time;
  - the list of unfinished transfers, newest first by start time.
- All three now use the order in which the rows were written, `transfer_log.id`. The
  shared database numbers the rows in that order whatever the clocks say. A check
  before delete names its archive, so it is always written after it.
- Synchronised clocks are no longer needed by the app. The times on screen still come
  from each PC's clock. The user guide recommends automatic time setting, or the NAS
  as the time server on a network without internet.

Affects: SPEC section 8, `transfer/delete.py`, `db/repository.py`, the user guide.

## D75. File identity in the transfer checks

Found in the release review (finding 1 of
`docs/reports/2026-10-11-release-review.md`). The user approved the fix on 2026-10-11.

- The destination checks compared path text only. One folder can have two names, for
  example a NAS reached by host name and by IP address, or a directory junction. A
  recording logged under one name and archived to the other passed every check. The
  archive copied nothing, and verification and Check before delete compared each file
  with itself. Delete laptop copy then deleted the only copy.
- The app now also compares file identity, as `os.path.samefile` reports it
  (`location.same_file()`):
  - The destination check refuses a destination that is the source folder, or that
    lies inside it, under another name. It also refuses a source folder that lies
    inside the destination under another name, and a target file already in place
    that is the source file itself.
  - Verification fails a destination file that is the source file. This covers the
    check after a copy, Check before delete and Compare with laptop copy.
  - Delete keeps a laptop file that is its own NAS copy. It also keeps a file when
    the identity of either file cannot be read.
- On Windows the identity is the volume serial number and the file ID. Over SMB the
  NAS reports them. A NAS with unreliable file IDs could make two different files
  look like one. The transfer is then refused, and nothing is deleted. The next visit
  to the NAS checks that a normal archive still passes.

Affects: SPEC section 8, `location.py`, `transfer/pathcheck.py`, `transfer/verify.py`,
`transfer/delete.py`.

## D76. An edit saves only over the entry it opened

Found in the release review (finding 2 of
`docs/reports/2026-10-11-release-review.md`). The user approved the fix on 2026-10-11.

- Edit mode writes every column of a recording, including its location, archive state
  and the channels' counts and times, as they were when the edit opened (D16). An
  archive, a Check archive or another edit that finished in between was undone by the
  save. After an archive and a delete, the recording pointed at a laptop folder that
  no longer existed.
- The save now reads the stored entry again inside its transaction. If any value that
  an edit can change differs from the entry the edit opened, the save writes nothing.
  The Log tab says that the recording changed, keeps the form, and asks the user to
  open the entry again.
- The comparison uses the same values as "No changes to save" (D47), so it does not
  depend on `updated_at`, which has whole seconds only.

Affects: SPEC section 6, `entry.py`, `db/repository.py`, `gui/log_tab.py`.

## D77. Version 1 schema frozen

Closes O20. The user approved it on 2026-10-20, as the first task after release
1.0.0. The real catalogue was made with the 1.0.0 build, and the pilot passed.

- `tests/schemas/v1.sql` holds `schema.sql` as released in the tag `v1.0.0`. A test
  checks its SHA-256, so the frozen copy cannot change without a failing test.
- A test builds a database from `v1.sql`, runs `migrations.upgrade()`, and compares
  it with a database built from the current `schema.sql`: tables and their columns
  (type, not null, default, primary key), indexes and their columns, and triggers.
  After a migration, this test shows that the migration leads to the current schema.
- While `LATEST_VERSION` is 1, a second test requires that both files build the same
  statements in `sqlite_master`. A change to a table, index or trigger in place
  fails it. Comments outside the statements may change.
- The comparison after an upgrade does not cover CHECK constraints or the text of
  triggers. A migration that changes either one needs its own test.
- D4 no longer allows edits in place. Every change to `schema.sql` comes with a
  numbered migration, a higher `LATEST_VERSION`, and the "Upgrade database" action
  (O19).

Affects: SPEC section 3, `schema.sql`, `db/migrations.py`, `db/version.py`,
`tests/schemas/v1.sql`, `tests/test_schema_freeze.py`.

## D78. Viewer filters with several choices

Closes O38. The user asked for it on 2026-10-12 and approved the proposed default
with the plan for version 1.1 on 2026-10-20. Amends D43 and replaces the Viewer
filter of D73.

- The site, project and band filters are drop-down lists with a tick box per entry.
  Nothing ticked means all, and the closed list then shows "All sites", "All
  projects" or "All bands". Otherwise it shows the ticked names, separated by commas,
  and its tooltip lists them.
- A click on an entry ticks or unticks it and leaves the list open. The Space key
  does the same for the current entry.
- Several choices in one filter match any of them. Different filters must all match,
  as before.
- The project list holds "No project" as one entry, so it combines with projects:
  "No project" and "Radar Trial" show the recordings of Radar Trial and those without
  a project.
- Several bands still match on the same channel as the centre frequency range (D43).
  Bands compare without letter case, as before.
- `RecordingFilter` holds `site_ids`, `project_ids` and `bands` as tuples, with
  `without_project`. The SQL uses `IN (...)`. A project filter with "No project"
  joins the two conditions with OR.
- After a Refresh, entries that are still in the database stay ticked.
- Filters still apply on Apply or Enter, and Clear unticks every entry.

Affects: SPEC section 5, `models.py`, `viewer.py`, `db/repository.py`,
`gui/viewer_tab.py`, `gui/widgets/check_combo.py`, the user guide.

## D79. A new folder keeps the previous entry's fields

Closes O43. Replaces D26. The user asked for it on 2026-10-20: retyping every field
after each folder made logging several folders slow. The user approved the plan on
2026-10-20.

- When the folder of a new entry changes, only the values that come from the scan
  are reset: start and end, the channel rows with their file counts and coverage, fs
  and the file duration. fs is filled in again from the next scan (D21). The file
  duration is set again from its file names (D22).
- Everything else stays: logged by, site, project, plan reference, remarks, sample
  type, IQ layout, endianness, header bytes, the band and fc of each channel, and the
  RF chain rows.
- Band and fc are kept by channel number. They wait in the form until the scan shows
  the channel rows.
- After the scan, the kept band, fc and RF chain rows of a channel that the new folder
  lacks are removed from the form. The message line names the channel and what was
  removed. They do not come back for a later folder that has the channel. The user
  left this question open in the plan, and the plan's default applies.
- Before the first scan of a new entry, the checklist does not check RF chain rows
  against the channels, because the channels are not known yet.
- A note in the "Before saving" panel, with the information mark and colour, names the
  kept format and counts the kept channel settings and RF chain rows. It asks the user
  to check them, and the site, project, plan reference and remarks, for this folder.
  It shows only when something other than the defaults was kept, and not in edit
  mode.
- Clear form still resets every field.
- Edit mode is unchanged: its folder cannot change (D16).
- The risk that D26 fixed comes back in part. A sample type kept from an `int8`
  folder fills in fs for `int8` in the next folder. The note names the kept sample
  type, and the checklist names the basis of each filled-in fs (D21), so the user can
  see it.

Affects: SPEC section 6, `entry.py`, `gui/log_tab.py`, the user guide.

## D80. Log tab templates in files

Closes O44. The user asked for it on 2026-10-20, for common hardware set-ups such as a
USRP and its antennas. The user chose files over a table in the catalogue, and asked
that a template can hold any field, site and project included, with the fields chosen
on export.

- A template is a TOML file with `format_version = 1`. Teams share templates by
  keeping the files in a common folder. The catalogue does not change, so no
  migration is needed.
- A template can hold any field the user types: logged by, site, project, plan
  reference, remarks, the file format (sample type, IQ layout, endianness, header
  bytes), band and fc by channel number, and the RF chain rows. It never holds a value
  from the scan: start and end, file counts, fs, file duration, or the folder and its
  location.
- Every field is optional. "Export template..." opens a dialog with one tick box per
  field group. Each box shows the form's current value or a count. Empty fields start
  unticked, and Save needs at least one ticked box. Blank RF chain rows, and channels
  with neither band nor fc, are left out.
- "Import template..." changes only the fields the file holds. RF chain rows in the
  file replace the form's rows; a file without RF chain rows leaves them. Band and fc
  go to the rows of the same channel number, and wait for a later scan for channels
  not shown yet (D79). The message line names the fields that were set.
- Site and project are stored by name, because ids differ between catalogues. Import
  matches them without letter case. A name the catalogue does not hold is not added:
  the field stays as it was, and the message line names it. An empty project means
  "no project". The user left the question of adding names open, and the plan's
  default applies.
- In edit mode, import follows D16: a sample type or header from a template needs a
  rescan before the save.
- A file that is not a template, comes from a newer version, holds no field, holds an
  unknown entry or a wrong value is refused with a plain message, and the form does
  not change.
- Export writes `<name>.new` next to the chosen file, reads it back, and then renames
  it over the chosen file. The file dialog does not ask about an existing file; the tab
  asks once, defaulting to No. The file dialogs start in the folder used last in the
  session. The app keeps no setting for it, because Qt's settings store would write to
  the Windows registry, also in tests.

Affects: SPEC sections 4 and 6, `templates.py`, `gui/log_tab.py`,
`gui/widgets/template_fields.py`, the user guide.

## D81. A queue in the Archive / copy tab

Closes O45 and O41. The user asked for it on 2026-10-20: each archive had to wait for
the one before it. The user chose these points: Pause stops the running item safely
and Start resumes it; recordings come from a Viewer multi-selection. The user asked
how per-item settings and several NAS locations work; the answer below was part of
the approved plan. The agent recommended which operations a queue holds.

- The tab has a Queue group. Its table lists each item's recording, state, operation,
  size, scope and destination. A line under the table shows the selected item's
  state in full.
- **Adding from the Viewer.** The recordings table allows several selected rows. A new
  "Add to queue" button offers "Archive or copy" and "Check archive".
  - "Archive or copy": a recording on the laptop is archived to the queue's "NAS
    folder for archives" plus its relative path. An archived recording is copied to
    the default copy folder plus its relative path (D60). Both take the whole
    recording, with the check mode chosen in the tab.
  - "Check archive" adds a Check archive of each archived recording (O41).
  - A recording that cannot be added is named with the reason, for example when no
    NAS folder is chosen.
  - Edit entry, Archive / copy, Scan for gaps and Open folder need exactly one
    selected recording. The details show the current row.
- **Adding from the form.** After a passed preview, "Add to queue" sits next to Run. It
  adds the transfer as set in the form: operation, channels, time range, destination
  and check mode.
- **Per-item settings.** Each item holds a whole transfer request. Edit takes an item
  out of the queue and back into the form, which previews it again. "Add to queue"
  then puts it back in the same place. Different NAS folders, channel subsets and time
  ranges are set this way. An archive is always the whole recording (D50).
- **Repeats.** An item that repeats a waiting, running or paused item is refused: an
  archive or a Check archive of the same recording, or any item to the same
  destination folder. Two copies of one recording to different folders are allowed,
  for example channel 0 to one folder and channel 1 to another. (Changed on
  2026-10-21: the first build refused every second copy of a recording.)
- **Previews.** New archives and copies from the Viewer are previewed when they join
  the queue, if the tab is idle, for their size and any problem. Every archive and
  copy is previewed again just before it runs: the source is scanned again (D53), and
  the destination and the free space are checked at that moment. A preview with
  errors marks the item "Not started" with the reason, and the queue moves on.
- **Running.** Start runs the waiting and paused items one after another. A failed item
  is marked and the queue moves on. While the queue runs, the form and the other
  buttons stay locked as for one operation, the Settings tab waits, and the Viewer's
  "Archive / copy" waits. Waiting items can be removed, and more can be added from the
  Viewer.
- **Check before delete.** With "After each archive, run Check before delete" ticked
  (the default), a passed archive is followed by Check before delete (D55) in the
  item's check mode. "Sizes only" skips that check and says why. Delete laptop copy
  stays a separate action for one recording, which asks first.
- **Pause.** Pause asks first, with default No. It cancels the running item between
  chunks, as Stop does: files already copied stay, and the log row is finished as
  `skipped`, so the item is also listed under "Unfinished transfers". Start continues
  with that item; its new preview finds the copied files and skips them (D51). With a
  hash check those files are hashed on both sides again (D63). The engine has no
  pause of its own, because a copy held open for a long time could meet network
  timeouts.
- **Memory only.** The queue is not saved. Closing the window while it runs asks first,
  as for one operation, and pauses it. Closing with items that have not run asks
  first too. The decision avoids a new file format and its recovery rules.
- `transferqueue.py` holds the queue and `run_item()`, without Qt. `run_item()` calls
  `preview_transfer()`, `run_transfer()`, `check_before_delete()` and
  `check_archive()`, and adds no code that copies, renames or deletes a file.

Affects: SPEC sections 5 and 8, `transferqueue.py`, `gui/transfer_tab.py`,
`gui/viewer_tab.py`, `app.py`, the user guide.

## D82. Values from the recorder's log

Closes O46. The user asked for it on 2026-10-21 and chose these points: the RF chain
names "USRP", "USRP Gain" and "Clock reference"; no row for the antenna port; a file
count that differs from the recorder's is information only.

- The team's recorder writes three files at the top of a recording folder:
  `recorder_<folder>.log` (the command line, the device, and per channel the actual
  rate, frequency and gain), `log.txt` (the command line) and `check_quick.txt` (the
  recorder's own check). The user's two examples of 2026-10-12, with paths and the
  account name replaced, are in `tests/data/recorder/`.
- `*.txt` and `*.log` files at the top of a recording folder are side files. The scan
  lists them with their sizes and no longer reports them as "not recognised". Deeper
  ones stay unrecognised.
- After the scan of a new entry, the Log tab fills from the log, once per folder:
  - fc and fs per channel, from "Actual RX Freq" and "Actual RX Rate". The block that
    starts "Using channel N" belongs to channel folder N.
  - the sample type: `sc16` is `int16`, `sc8` is `int8`, `fc32` is `float32`.
  - "USRP Gain" in dB: one Recording row when every channel has the same gain, else a
    row per channel. It replaces every "USRP Gain" row of the form.
  - "Clock reference": GPSDO, Internal or External, from the clock source.
  - "USRP", as the log names the device, for example "X310 + UBX", only when the form
    has no "USRP" row. The log cannot tell a USRP-2954 from an X310 with UBX boards,
    so a row set by a template or kept from the previous entry stays.
- Where the main log lacks a value, the command line in `log.txt` gives the requested
  one.
- Log values replace values kept from the previous folder (D79) or set by a
  template (D80), because they describe this folder. fc and fs from the log show in
  italics with a tooltip, like a filled-in fs (D21), until the user types in the
  field. A rescan of the same folder does not fill again, so edits stay.
- Edit mode never fills from the log. It shows the information lines.
- Not stored: the antenna port, the LO offset, buffer settings, the UHD version and
  the recorder build. They stay in the log files, which D83 copies with the data.
- Information lines in the checklist, none of which blocks saving: what was filled;
  the recorder's verdict; times taken from the PC clock; GPS not locked; restarts; a
  stop reason other than normal; a total file count that differs from the
  recorder's "Files written". The count can differ for a reason, such as files
  removed on purpose, and the files cannot be recovered by refusing the entry.
- A log that cannot be read or chosen (several `recorder_*.log` and none named after
  the folder) fills nothing and gives one information line.
- `recorderlog.py` holds the reading, without Qt.
- **Changed on 2026-10-22** (review of 1.1.0, finding 3): the gain row is named "USRP
  gain", the spelling of the real catalogue. "USRP Gain" made the checklist report
  on every scan that the save would change the spelling. Each of the three names
  takes the catalogue's spelling when the catalogue holds the name in another
  letter case (D28). D87 covers a template imported after the log filled the form.

Affects: SPEC sections 6 and 7, `recorderlog.py`, `scan/scanner.py`, `entry.py`,
`gui/log_tab.py`, `diagnostics/fixtures.py` (its junk file is now `notes.md`), the
user guide.

## D83. The recorder's log files travel with the recording

Closes O47. Found while assessing O46: archives and copies took only the data files,
so the recorder's logs stayed on the laptop and never reached the NAS. The user asked
on 2026-10-21 that every `*.txt` and `*.log` file at the top of the recording folder
is copied and archived with the data.

- The side files of D82 join every selection: whole archives, whole copies, and copies
  of some channels or a time range, because they describe the whole recording.
- They are copied, checked and listed in the manifest like data files. A transfer's
  file count and size include them, and the preview names them in one line.
- Delete laptop copy deletes them with the data, through the same per-file checks
  (D52, D55, D75), because the manifest lists them. The laptop folder is then empty
  and is removed.
- An archive made before this change lists no logs. Its Delete laptop copy keeps the
  logs, so the laptop folder keeps them and stays.
- A log already at the destination with the source's size counts as copied (D51). A
  log that changes after the preview fails the check after the copy, as a data file
  does.
- Check archive and Compare with laptop copy still compare the channels only. A laptop
  copy made before this change may lack the logs.
- No change to the copy engine, the verification or the delete module: the selection
  now holds the side files, and those parts work on the selection's file list.

Affects: SPEC section 8, `transfer/selection.py`, `transfer/operations.py`
(`compare_with_laptop`), `movecopy.py`, the user guide.

## D84. The Log tab's message line shows its state

Closes O48. Found in the user's manual test of 2026-10-22: every message under the
Log tab's buttons was plain text, so "Template not loaded" looked like "Template
saved". The other tabs already colour their message lines.

- Each message carries a state, shown with the checklist's mark and colour, which
  suit the light and the dark theme (D38):
  - ✓ green for success: saved, changes saved, site or project added, template saved,
    template loaded with every name found;
  - ⓘ amber for information: a template that names a site or project the catalogue
    lacks, values of a missing channel removed, no changes to save, nothing saved
    after No, "Template not saved." after No;
  - ✗ red for failure: not saved, cannot open or read, folder cannot be logged,
    template not loaded or not saved;
  - ○ grey for something still to do: no database, choose a folder first, complete
    the checklist first.
- "Saving..." stays plain.
- The colour follows a switch between the light and the dark theme.

Affects: SPEC section 6, `gui/log_tab.py`.

## D85. An archive whose check is still needed

Closes O49. Amends D81. Found in the user's manual test of 2026-10-22, step 4.12: three
queued archives passed, their Check before delete then failed, and the queue showed
each as ✗ Failed. The user took the archives for failed until the Viewer showed them
archived. The user chose these points on 2026-10-22.

- A queue item whose archive passed but whose Check before delete did not pass gets
  the state ⓘ "Archived, check needed", in amber. That covers a check that failed, a
  check that was stopped, a check that could not run (for example a read error, or
  the archive's file list refused), and a check skipped because the check mode was
  "Sizes only".
- Its note says that the recording now points at the NAS copy, that the laptop copy
  stays, why the check did not pass, and to run Check before delete in the form.
- The end-of-queue summary counts these items apart and is amber, not red. Parts of
  the summary are separated by ";" because the state's name holds a comma.
- Clear finished keeps these items, as a reminder that their laptop copies cannot be
  deleted yet; Remove takes one out; Start skips them; Edit is disabled for them.
  The queue is not saved (D81), so the lasting record is the recording's history and
  the Archive / copy tab.
- ✗ Failed stays for a copy or the check after the copy that failed.
- No "Check again" action for now (the user's choice).
- **Found at the same time:** Check before delete through a Windows share of the same
  PC does not fail for every file, as Milestone 8 recorded. In the test, files of
  64,000 bytes (a multiple of 512) were read; files of 4,000 bytes were refused with
  WinError 87. The share most likely refuses reads past the cache of files whose
  size is not a multiple of 512 bytes. The real NAS read 1,000,000-byte files and a
  500,000-byte last file in the field test of 2026-10-05, so it does not share this
  limit. The recorder's log files (D83) have any size, so the pilot checks a delete
  of an archive with log files on the real NAS.

Affects: SPEC section 8, `transferqueue.py`, `gui/transfer_tab.py`, the user guide,
`docs/STATUS.md` (notes for agents, pending checks).

## D86. A paused queue item continues in the queue only

Amends D81. Found by the user after the review of 1.1.0 (finding 10). The user
approved the plan on 2026-10-22 and asked for the Resume label.

- In 1.1.0 a paused item could be continued three ways: Start in the queue, Run in
  the form (its preview stayed when the item came from the form), and Resume under
  "Unfinished transfers", which loads the item's stopped row into the form. The form
  did not know about the queue item. An archive finished with Run left the item
  "Paused"; Start then marked it "✗ Not started: The recording is already archived".
  A copy finished with Run was copied again by Start, which copied no file and
  recorded a second transfer. No file was at risk: the copier skips a file already in
  place with the right size.
- The form's Run and Add to queue stay disabled while the queue holds a waiting,
  running or paused item that the form's transfer repeats. "Repeats" follows the
  queue's own rule (D81): an archive of the same recording, or any transfer to the
  same destination folder. A line under the buttons, with the information mark,
  says that the transfer is waiting or paused in the queue, and that Start or Resume
  runs it, or Remove frees it for the form.
- The button under "Unfinished transfers" that loads a stopped transfer into the form
  is renamed from Resume to **Open in form**, so that it does not share a name with
  the queue's Resume (the user's choice after the manual test of 2026-10-22). The two
  differ: the queue's Resume runs the queue, the paused item first; Open in form only
  loads one transfer and previews it, and Run in the form continues it. For a
  transfer the queue still holds, Run then stays disabled with the same line.
- While the queue holds a paused item, the queue's Start button reads **Resume**. The
  pause question, the end-of-queue summary and a paused item's note name Resume.
- The end of a queue run drops the form's preview, because the queue may have copied
  into its destination since the preview was made.
- The pause question also says that a pause during Check before delete stops the
  check, and the item becomes "Archived, check needed" (D85).

Affects: SPEC section 8, `transferqueue.py` (`TransferQueue.holding()`,
`has_paused()`), `gui/transfer_tab.py`, the user guide.

## D87. A template imported after the log filled the form

Amends D80 and D82. Found in the review of 1.1.0 (finding 2). The user chose the
pop-up on 2026-10-22.

- In 1.1.0, a template imported after the scan replaced values that the recorder's
  log had filled in for the folder. The fc kept the log's italics and tooltip, the
  log's RF chain rows were removed, and the checklist still named them as filled
  from the log. D82 says the log's values win, which held only for a template
  imported before the scan.
- When a template holds other values for fields the log filled in and the form still
  holds, a pop-up lists each one with both values, for example "fc of channel 0: log
  300 MHz, template 145.8 MHz". The fields are the sample type, the fc of each
  channel, and the log's RF chain rows ("USRP gain", "Clock reference", "USRP"). A
  template without one of those rows counts as a different value, because its RF
  chain replaces the form's rows.
- **Keep the log's values** (the default): the template fills in its other fields.
  Its band of a channel is used with the log's fc. Its RF chain rows join the log's
  rows; a template row with the name of a log row is left out.
- **Use the template's values:** the template fills in every field it holds. Its fc
  loses the log's italics and tooltip.
- **Cancel** (or Esc) changes nothing. The message line says "Template not loaded."
- The message line after an import names the fields kept from the log, or replaced
  by the template.
- The checklist line "Filled in from the recorder's log" names only what the form
  still holds from the log. A value typed over or replaced drops out of it.
- A value the user typed over no longer counts as from the log, so it gives no
  pop-up. A template imported before the scan gives none either: the log fills in
  afterwards and wins, as before. Edit mode never fills from the log, so it gives
  none.

Affects: SPEC section 6, `recorderlog.py` (`template_conflicts()`, `keep_log_values()`,
`still_filled()`), `gui/log_tab.py`, the user guide.

## D88. The band filled in from fc

Closes O50. Amends D19. The user asked for it on 2026-10-22 and chose these points on
2026-10-22 and 2026-10-23: the list lives in the code; the bands HF, VHF, UHF, L, S,
C, X, Ku and Ka, with UHF ending where L starts; K added between Ku and Ka; short
names; fc is the frequency on air.

- Band was free text, and the box listed only the bands already in the catalogue. In
  the manual test of 1.1.1, a new folder kept band UHF from the previous folder while
  its recorder's log set fc to 145.8 MHz (D79, D82).
- The list is fixed in `bands.py` and follows IEEE Std 521. Every PC on the same
  version uses the same list. Settings are per PC (D68), so a list in the settings
  would differ between PCs. A change to the list comes with a new release.

  | Band | From | Up to |
  | --- | --- | --- |
  | HF | 3 MHz | 30 MHz |
  | VHF | 30 MHz | 300 MHz |
  | UHF | 300 MHz | 1 GHz |
  | L | 1 GHz | 2 GHz |
  | S | 2 GHz | 4 GHz |
  | C | 4 GHz | 8 GHz |
  | X | 8 GHz | 12 GHz |
  | Ku | 12 GHz | 18 GHz |
  | K | 18 GHz | 27 GHz |
  | Ka | 27 GHz | 40 GHz |

- A band includes its lower edge and excludes its upper edge, so 300 MHz is UHF. The
  ITU's UHF runs to 3 GHz and would overlap L and S; IEEE Std 521 ends UHF at 1 GHz.
  The letter names are the IEEE radar bands. The NATO letter bands use some of the
  same letters for other ranges.
- K fills the range between Ku and Ka, so every fc from 3 MHz to 40 GHz has a band.
  An fc below 3 MHz or from 40 GHz has none.
- Where bands overlap, the narrowest band that holds fc wins, and a tie goes to the
  band listed first. The list above has no overlaps. The rule is there for a later
  band inside another, such as Marine VHF inside VHF.
- When fc changes, typed or set by the recorder's log or a template, an empty band,
  or the band of the previous fc, follows the new fc. An fc in no band clears it. A
  band the user typed or picked that differs from the previous fc's band stays. The
  rule needs no stored state: a band equal to the previous fc's band follows.
- A kept band (D79) follows the log's fc by the same rule. A kept UHF band that
  matched the previous folder's 433 MHz becomes VHF for 145.8 MHz.
- A template's band is applied after its fc, so the template's band wins. A template
  channel with an fc and no band leaves the band to the rule. Before D88, such a
  channel cleared the band.
- A new entry's empty band takes the band of a kept or template fc when the channel
  rows appear.
- Edit mode shows the stored band as it is, so opening an entry changes nothing. The
  rule applies when fc changes.
- A band filled in from fc is shown in italics, with a tooltip that names the band's
  range, until the user types or picks a band.
- When the band is one of the list and fc lies outside it, an information line says
  so, for example "Channel 0: fc 145.8 MHz is outside UHF (300 to 1000 MHz). Check
  the band." It does not block saving. A band not in the list gets no such line.
- The box lists the bands of the list in frequency order, then the other bands of the
  catalogue. Stored entries do not change, and the Viewer's band filter does not
  change.
- fc is the frequency on air. For a recording made through a down-converter, the
  recorder's log gives the frequency the USRP tuned to. The user types the frequency
  on air over it; the fc then loses the log's mark (D82), and the band follows.
- No schema change.

Affects: SPEC sections 6 and 9, `bands.py`, `entry.py`, `gui/log_tab.py`, the user
guide.

## D89. Deleting an entry added by mistake

Closes O39. Replaces D41. The release review (finding 15) and the user, on
2026-10-22, asked how an entry logged by mistake is removed. The user chose these
points on 2026-10-23: the action sits in the Log tab's edit mode, and a copy of the
entry is saved as a file on the PC that deletes it.

- Under D41, removing an entry was a manual database job, and
  `repository.delete_recording()` refused any recording with a `transfer_log` row.
  Every entry logged in place on the NAS has the row of D2, and so does every legacy
  import (D66), so the function refused all of those.
- **Which entries can be deleted.** An entry whose history holds only check rows
  without a parent: the row of D2, Check archive and Compare with laptop copy. These
  rows describe the entry and go with it. Any archive, copy or delete row keeps the
  entry, and so does a check before delete, which always follows an archive. The
  history of a transfer then stays, with its manifest. `repository.blocks_deletion()`
  holds the rule.
- **Also refused:** an entry that this PC's Archive / copy queue holds as waiting,
  running or paused, and an entry the Archive / copy tab is working on. The message
  names the reason and what to do first.
- **The action.** "Delete entry..." in the Log tab, shown in edit mode only. The
  user reaches it from the Viewer's Edit entry, or from "Edit existing entry" after a
  scan. The Viewer stays read-only (SPEC section 5).
- **The question.** "Delete entry?" names the recording number, the folder, the start
  at the display offset, the number of channels and files, how many check results
  are deleted with the entry, and where the copy is saved. It says that the files in
  the folder are not touched. The buttons are "Delete entry" and Cancel, and Cancel is
  the default.
- **The steps.**
  1. A worker reads the stored entry and its rows again. It refuses an entry that
     changed after edit mode opened it (D76), and an entry with a blocking row. The
     question follows.
  2. The copy of the entry is written to a new file,
     `deleted-entries/recording-<id>-<UTC time>.json`, next to the settings file, as
     for manifests (D52). It holds the database path, the time, who deleted, all
     fields, the channels, the RF chain and the check rows. An existing file is never
     replaced. If the copy cannot be written, nothing is deleted.
  3. One write transaction reads the entry and its rows again, refuses if either
     differs from step 1, and deletes the check rows and the recording. Channels and
     RF chain rows go by cascade. `transfer_log` has no cascade, so the check rows are
     deleted first. If this step fails, the message names the copy and says that the
     entry was not deleted.
  4. The form is cleared. The message line says "Deleted recording 12 from the
     catalogue. Its files were not touched. A copy of the entry is in …". The Viewer
     refreshes, and the Archive / copy tab drops the recording from its form.
- **No file of the recording is touched.** The delete removes catalogue rows only.
  `transfer/delete.py` stays the only module that deletes files.
- **Two PCs.** A copy or an archive writes its `transfer_log` row before its first
  file. A delete that comes later finds that row and is refused. If the delete comes
  first, the transfer's row fails on the foreign key, and the transfer stops with
  "Recording 12 is no longer in the catalogue. It may have been deleted on another
  PC." before it copies a file. A save in edit mode, and a second delete, of an entry
  deleted on another PC give the same message.
- **The copy stays on the PC that deleted.** A shared record would need a new table,
  so schema version 2 and a migration (HANDOFF.md, section 5). The user chose the
  file.
- No schema change.

Affects: SPEC sections 3, 5, 6, 9 and 13, `db/repository.py` (`blocks_deletion()`,
`delete_recording()`, `insert_transfer()`), `entry.py` (`check_deletion()`,
`delete_entry()`), `deletion_record.py`, `gui/log_tab.py`, `gui/transfer_tab.py`,
`app.py`, the user guide.

## D90. Logging several folders with one set-up

Closes O51. The user asked for it on 2026-10-22: recordings with one set-up at
different times and frequencies are common, and logging each folder on its own was
quick but tedious. The user approved the plan on 2026-10-23 and chose these points:
a folder is fixed in place in the form; each entry is saved on its own; a template
sets the shared fields only, and each folder's log wins without a question; the
folders of a session are subfolders of one folder; 10 to 50 folders in a batch, each
up to a couple of hours.

- **Mode.** Section 1 of the Log tab offers "One folder" (the form as before) and
  "Several folders". Switching keeps the shared fields, as a new folder does (D79).
  Switching back with folders not yet saved asks first, defaulting to No. Edit mode,
  Delete entry (D89) and "Use parent folder" (D27) belong to "One folder" mode; edit
  mode opened from the Viewer switches back.
- **Choosing folders.** "Add folders..." asks for a folder and lists its subfolders
  that hold a channel folder or a data file at their top, sorted by name. A folder
  already in the list is not added again. A folder that is itself a recording (its
  numbered subfolders are channel folders) gives a line and a button "Add it as one
  recording". The listing runs in a worker, because the folder may be on the NAS.
- **Scanning.** The added folders are scanned at once, one after another in the
  worker; "Scan folders" scans every unsaved folder again. Each scan also reads the
  folder's recorder log and checks the catalogue (already logged, D61). A folder's
  result reaches the list as soon as it is scanned. The line reads "Scanning folder 3
  of 12: 12,345 files found". Cancel stops the folder being scanned; the rest stay
  "Not scanned". A rescan drops what was typed for that folder's channels. After the
  scan, the list is sorted by start time.
- **Values per folder.** Each folder's scan and log give its start and end, the
  channels with fc and fs, the band from fc (D88), the sample type, the RF chain rows
  "USRP gain", "Clock reference" and "USRP" (D82), and the file duration from its file
  names (D22). These values win over the shared ones. Where a folder has no log, fs is
  filled in from the file size with the shared format (D21), and fc is to be typed.
- **Shared values.** Sections 2, 3 and 5 hold what the user types once: logged by,
  site, project, plan reference, remarks, the format, and the RF chain rows. The file
  duration field shows the selected folder's value and cannot be changed in this
  mode.
- **Fixing one folder in place.** Selecting a folder in the table shows its times,
  location and channels in sections 2 and 4. fc, band and fs typed there belong to
  that folder, with the marks of D21, D82 and D88 kept per folder.
- **The folder table** is the preview: a tick box "Save", folder, start and end at the
  display offset, channel count, fc, band, fs, sample type, files, size, and a state
  with the checklist's mark and colour: ready, ready with notes, to do, errors, not
  scanned, saved as recording N, not saved with the reason. A folder that is already
  logged starts unticked.
- **Checklists.** The side panel shows the checklist of the list: the number of ticked
  folders ready to save, each to-do item or error that every ticked folder shares once
  ("Choose a site (all 12 folders)"), and the other to-do items and errors with the
  folder's name. Below it, the full checklist of the selected folder, as the
  one-folder form gives it, plus a line for another folder in the list with the same
  start, end and channels (D61). Each folder's checklist is kept until its inputs
  change; the remarks and the plan reference are not inputs of any check.
- **Saving.** "Save 12 entries" is enabled when at least one ticked folder has no
  to-do item and no error. A question names the number of entries, the site, project
  and logged-by name, the time span and total size, and the folders left out; Save is
  the default. Each entry is saved in its own transaction by `entry.save_new()`, one
  after another, so a folder that fails (for example one logged meanwhile on another
  PC) does not stop the rest. Saved folders show "Saved as recording N" and cannot be
  changed; a folder not saved shows its reason, and Save saves only what is left. The
  message line gives the result, and the Viewer refreshes once.
- **Templates.** A template sets the shared fields only. Its band and fc are not used,
  and each folder keeps its log's values without the question of D87. The message line
  says so.
- **Closing.** Closing the window and a new database in the Settings tab ask first
  while the list holds folders not yet saved. The list is not kept. Clear form empties
  the list without a question, as it clears the form in "One folder" mode.
- **Size.** On the development PC (local disk), 50 folders of 2 channels by 7,200
  files scanned in 2.9 s, and the list held 103 MB. A scanned channel keeps its size
  counts and close file pairs, counted in the scan's worker, so the checklists of all
  50 folders take about 52 ms on the main thread after a change to a checked field,
  and 3 ms after a change to the remarks. The report gives the measurements.
- No schema change. `batchlog.py` holds the logic without Qt; `gui/widgets/folder_table.py`
  the table.

Affects: SPEC sections 6 and 9, `batchlog.py`, `gui/log_tab.py`,
`gui/widgets/folder_table.py`, `app.py`, the user guide.
