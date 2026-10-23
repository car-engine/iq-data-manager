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
3. **Archive / copy**: archive recordings to the NAS, or copy whole recordings or time
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
| `projects` | Selectable project names, unique case-insensitively. Users can add new ones (D73). |
| `recordings` | One row per capture session: envelope times, site, project (optional, D73), file format, storage location, archive state, plan reference, remarks, and `created_at` and `updated_at` (a trigger sets `updated_at` on every update; the Viewer shows it, D47). |
| `channels` | One row per channel: index, subfolder, band, fc, fs, own start/end, file count, bytes. Single-channel recordings have one row (index 0). |
| `recording_params` | Flexible RF chain key/value rows. `channel_id` NULL = whole recording, set = one channel. |
| `transfer_log` | History of archives, copies, archive checks and deletions of laptop copies, including time ranges, channel subset, hash mode, verification result and the path of each transfer's manifest. A delete row, and a check before delete, name the archive they follow in `parent_id` (D52, D55). `dismissed_at` records "Forget" on an unfinished copy or archive. |

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
  without explicit handling. `repository.delete_recording()` deletes the recording's
  check rows without a parent first, and refuses a recording with any other row
  (D89; section 6).
- **Schema version**: `PRAGMA user_version`. Changes are numbered migrations in
  `src/iqdm/db/migrations.py`. They run only from an explicit, user-confirmed
  upgrade action, with a backup copy made first (DECISIONS.md D6). Version 1 is the
  schema of release 1.0.0, frozen in `tests/schemas/v1.sql` (D77). A change to
  `schema.sql` comes with a numbered migration, and a test checks that a version 1
  database, upgraded, has the structure of the current `schema.sql`. A file at the
  current version that lacks a table or column of `schema.sql` counts as an older
  version (D73).

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

Log tab template files (section 6, D80) are TOML files too, but they are not
configuration: the app reads one only when the user imports it.

**Defaults file** (D68). The packaged app looks for `defaults.toml` in the folder of
`IQDataManager.exe`. While the settings file in use does not exist, the app reads its
settings from `defaults.toml`, which has the same format and rules. The Settings tab
names the defaults file, and Save writes the values to the settings file. From then
on that PC ignores the defaults file. The app never writes `defaults.toml`. The build
folder holds `defaults.example.toml`, which whoever prepares the build fills in and
saves as `defaults.toml`. The app run from source has no defaults file.

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
copy_workers = 4                  # files copied at once; 1 to 16 (D58)

[storage_roots]                    # UNC root -> local path override (Linux later)
# '\\192.168.1.50\recordings' = '/mnt/nas/recordings'
```

### Settings tab (Milestone 3a)

A fourth tab, "Settings", after "Archive / copy" (DECISIONS.md D29, D30). It edits
`config.toml` and shows the state of the database. Decisions D31 to D38 settle its
details. The milestone is "Milestone 3a" (D32). Its text follows CLAUDE.md, "User-facing
text": no key names, decision numbers or database internals on screen (D38).

| Section | Fields and actions |
| --- | --- |
| Database | "Database file" (`db_path`), with Browse for an existing `.db` file and "New database..." for a new, empty one (D67). New database asks for a file that does not exist, asks Yes/No first (default No), creates the file in a worker and puts its path in the field; Save switches to it. A status line in green, amber or red with a mark (D38): ready to use; no path, checking, or a newer database the app can only read; missing, a folder, unreadable, not an IQ Data Manager database, or an older database. The tooltip holds the schema version and connection settings (`connection.inspect_database()`). The check runs when the tab opens, after Browse, when the path field loses focus, and on "Check connection". It uses a read-only connection. |
| NAS locations | The `nas_roots` list, with Add, Edit and Remove. Each entry must pass `config.is_unc_path()`. A line explains the rule in plain words: folders under these locations count as already archived on the NAS (D14, D2). |
| Display | "Show times at UTC offset" (`display_utc_offset_hours`), from −12 to 14 in steps of 0.25 (D24), with an example such as "2026-09-30 02:00:00 UTC is shown as 2026-09-30 10:00:00 (UTC+8)." "Highlight coverage below" (`coverage_highlight_percent`), from 0.0 to 100.0 % with one decimal place; 0 is an error (Milestone 4, D39). |
| About | The path of the settings file in use, with "Open folder". The app version. A note when `--config` or `--db` is in force. |

Milestone 3a added the first three keys, and Milestone 4 added the coverage threshold
(D34, D39). Milestone 6 adds a "Transfers" section with `default_local_copy_root`,
`network_speed_mb_s`, `default_hash_mode`, `hash_sample_fraction`,
`free_space_margin_gb` and `copy_workers` (D34, D58). Milestone 5 read them from the
file only.

Not in the Settings tab (D30):

- **"Upgrade database".** It waits for the first real schema migration (O19). Until
  then an older database gives a red status line that says this version of the app
  cannot open it (D37, D38).
- **Data-file extensions.** They stay fixed in code as `.dat` and `.bin`
  (`scanner.DEFAULT_EXTENSIONS`, any letter case), so every PC scans a folder the same
  way. A new extension comes with a new release.
- **Creating the shared catalogue.** It comes from the legacy import (section 10,
  D66). "New database..." makes an empty database for a private project (D67).

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
- **Unsaved changes** (D70). While the fields differ from the file, the tab's title is
  "Settings (not saved)". Leaving the tab asks first: Save, Leave without saving
  (the fields return to the saved values) or Stay. With a wrong value in a field,
  only Leave without saving and Stay are offered. Closing the window asks the same
  question, with "Close without saving".
- **Overrides.** `--config` and `--db` keep working. With `--db`, Save writes
  `db_path` to the file, and the `--db` path stays in force for the current run. The
  tab says so in amber with the ⓘ mark, as it does for the defaults file (D69).
- **Startup errors.** A configuration file that cannot be read opens the app on the
  Settings tab with the error shown, so the user can correct it there. A file that is
  not valid TOML can be replaced by Save.
- **Database files.** The Settings tab creates a database only through "New
  database..." (D67), and never changes one. It opens the chosen file read-only.
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
  "to" date includes its whole day), site, project, band, centre frequency range in
  MHz (band and range match on the same channel), archive state, "RF chain contains"
  (a parameter's name, value or unit) and "Remarks contain". Site, project and band
  are lists with a tick box per entry (D78). Nothing ticked means all. Several ticked
  entries match any of them. The project list holds "No project" as one entry, which
  combines with projects (D73, D78). Filters apply on Apply or
  Enter, and Clear removes them. A wrong value is marked under the filters and runs
  no query. The filter runs in SQL (D40).
- **Recordings table**: ID, start at the display offset, site, project (empty when
  none), channel count, centre
  frequencies in MHz ("433.92 × 2" when all channels share one), span, coverage
  (minimum across channels), total size, archive state, logged by. Every column
  sorts, numbers as numbers. The model sorts its own rows (D40).
- **Marks**: coverage below `coverage_highlight_percent` is amber with the ⓘ mark
  (D39). An archived recording logged in place on the NAS shows "archived, not
  verified" in amber (D2, D44), until a "Compare with laptop copy" passes (D56). A
  coverage or size that the database does not hold
  shows "unknown".
- Selecting a recording shows its channels table (index, band, fc, fs, start, end,
  files, coverage) and the details panel for the recording. Selecting a channel
  narrows the details to that channel.
- **Details panel**: the RF chain that applies (Recording rows, with a channel's own
  rows replacing Recording rows of the same name and naming the replaced value; D28),
  full path of the recording or channel, format, project, plan reference, remarks, who logged
  it and when, when it last changed (`updated_at`, shown when it differs from the
  logging time; D47), the "not verified" note, and the transfer history in the order
  the rows were written (D74).
- **Gap detail** (section 7): "Scan for gaps" reads the recording folder in a worker
  with the stored file duration, with progress and Cancel. It shows a coverage
  timeline per channel, the gaps per channel at the display offset (the first 10,
  then a count), and where the folder differs from the database: a channel missing on
  either side, a different file count or a different total size. The scan writes
  nothing.
- **Several recordings** can be selected (D81). "Add to queue" adds them all to the
  Archive / copy queue. The other actions need exactly one selected recording.
- **Actions** on the selected recording: Refresh (keeps the filter, the sort order
  and the selection), Open folder (the recording folder, or the channel folder when a
  channel is selected), Edit entry (D45: opens the Log tab in edit mode, and asks
  first when the Log tab form holds input that is not saved). "Archive / copy" comes
  with the Archive / copy tab in Milestone 6 (D42, D64). The Viewer does not delete
  recordings; the Log tab's edit mode does (D89, section 6).
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
   the Windows login name, editable), site (dropdown plus "Add site"), project
   (optional dropdown with an empty choice, plus "Add project"; D73), recording plan
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
   dropdown that lists the bands of D88 in frequency order, then the other bands
   already in the DB. The app fills it in from fc (below). fc is entered in MHz (D19)
   and is the frequency on air: for a recording made through a down-converter, the user
   types it over the tuned frequency from the recorder's log (D88). fs
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
- Another recording with the same start, end and channel indices is reported as
  information that names it (D61). It may be the same capture in another folder.
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
- **From the recorder's log** (D82), when the folder holds one, once per folder of a
  new entry: fc and fs per channel ("Using channel N" is channel folder N), the
  sample type (`sc16` int16, `sc8` int8, `fc32` float32), the RF chain rows "USRP
  gain" (one Recording row when all channels match) and "Clock reference", and
  "USRP" only when the form has none. Each name takes the catalogue's spelling when
  the catalogue holds it in another letter case. The main log is `recorder_*.log`;
  `log.txt` gives requested values it lacks. Log values replace kept values, and
  template values imported before the scan. fc and fs from the log are shown in
  italics until the user types in them; an fs from the log does not follow the
  format fields. Edit mode never fills. Information lines, which do not block saving,
  name what the form still holds from the log, the recorder's verdict, a time taken
  from the PC clock, GPS not locked, restarts, and a file count that differs from the
  recorder's.
- **The band from fc** (D88), from a fixed list in `bands.py` that follows IEEE Std
  521: HF 3–30 MHz, VHF 30–300 MHz, UHF 300 MHz–1 GHz, L 1–2 GHz, S 2–4 GHz, C 4–8
  GHz, X 8–12 GHz, Ku 12–18 GHz, K 18–27 GHz, Ka 27–40 GHz. A band includes its lower
  edge and excludes its upper edge. Where bands overlap, the narrowest band that holds
  fc wins, and a tie goes to the band listed first. When fc changes, typed or set by
  the log or a template, an empty band and the band of the previous fc follow the new
  fc; an fc in no band clears them. A band the user typed or picked that differs from
  the previous fc's band stays. A template's band is applied after its fc, so it wins.
  A new entry's empty band takes the band of a kept or template fc when the channel
  rows appear. Edit mode shows the stored band and applies the rule only when fc
  changes. A band filled in from fc is shown in italics until the user types or picks
  one. When the band is one of the list and fc lies outside it, an information line
  says so; it does not block saving.
- **A template imported after the log filled in** (D87): when it holds other values
  for the sample type, the fc of a channel, or the log's RF chain rows, a pop-up lists
  each with both values. "Keep the log's values" (the default) applies the rest of
  the template, with its RF chain rows added to the log's rows. "Use the template's
  values" applies all of it, and its fc loses the log's mark. Cancel changes nothing.

Choosing another folder for a new entry resets only the values that come from the
scan: start and end, the channel rows, fs and the file duration (D79). Every other
field stays: logged by, site, project, plan reference, remarks, the file format, the
band and fc of each channel number, and the RF chain rows. After the scan, the kept
values of a channel the new folder lacks are removed, and the message line says so.
A note in the "Before saving" panel names what was kept. Clear form resets every
field.

Templates (D80): "Export template..." saves fields of the form to a TOML file, and
"Import template..." fills them in again. A template can hold any field the user
types: logged by, site and project (by name), plan reference, remarks, the file
format, band and fc by channel number, and the RF chain rows. It never holds a value
from the scan. Every field is optional; export asks which fields to save, and import
changes only the fields the file holds. A site or project name that the catalogue does
not hold is named on the message line and not added.

A folder named like a channel folder (1 to 3 digits, such as `0`) gets an
information line and a "Use parent folder" button. It does not block saving (D27).

### Several folders (D90)

Section 1 offers "One folder", the flow above, and "Several folders", which logs many
folders with one set-up. The logic is in `batchlog.py` (no Qt).

- "Add folders..." lists the subfolders of a chosen folder that hold a channel folder
  or a data file at their top, and adds those not yet listed. A chosen folder that is
  itself a recording is offered as one recording. The added folders are scanned at
  once, one after another in a worker, with their recorder logs and the catalogue
  checks; "Scan folders" scans the unsaved ones again, and Cancel stops. After the
  scan the list is sorted by start.
- Each folder's own scan and log give start and end, channels, fc, fs, band (D88),
  sample type, the log's RF chain rows (D82) and the file duration (D22); they win
  over the shared fields. Sections 2, 3 and 5 hold the shared fields; the file
  duration field cannot be changed in this mode. Selecting a folder shows its times,
  location and channels; fc, band and fs typed in section 4 belong to that folder.
- Under section 5's shared rows, a read-only table lists the selected folder's RF
  chain rows from its recorder's log, in italics: the rows that folder is saved with.
  A line under it names the shared rows of the same name that they replace for that
  folder, and the log's sample type when it differs from section 3's. The table is
  hidden for a folder whose log gives none of these, and in "One folder" mode. To
  change such a value for one folder, the user unticks it and logs it in "One
  folder" mode (D93).
- The folder table shows per folder: a "Save" tick box, folder, start, end, channel
  count, fc, band, fs, sample type, files, size, and a state with mark and colour. An
  already logged folder starts unticked.
- The side panel shows the checklist of the list (folders ready, to-do items and
  errors shared by all ticked folders once, the others with the folder name) and the
  full checklist of the selected folder, which adds a line for another listed folder
  with the same start, end and channels (D61).
- "Save N entries" asks first, then saves each ready, ticked folder as its own entry
  in its own transaction. A failure is shown at its folder; the rest are saved. Saved
  folders cannot be changed, and Save saves only what is left.
- A template sets the shared fields only; each folder keeps its log's values, without
  the question of D87.
- Edit mode, Delete entry and "Use parent folder" belong to "One folder" mode.
  Leaving "Several folders", closing the window or a new database asks first while
  folders are not saved.

Save writes the recording, channels and params in one transaction and confirms it in a
pop-up. Edit mode loads an existing recording into the same form and updates it.

The message line under the buttons shows each message with the checklist's mark and
colour (D84): ✓ success, ⓘ information, ✗ failure, ○ still to do. "Saving..." is plain.

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
- A save writes nothing when the stored entry changed after the edit opened, for
  example through an archive, a Check archive or another edit. The tab says so, keeps
  the form and asks the user to open the entry again (D76). A save over an entry
  deleted on another PC says that the entry is no longer in the catalogue (D89).
- **Delete entry...** (D89), shown in edit mode only, deletes an entry added by
  mistake from the catalogue. Its files are never touched. It is refused when the
  entry's history holds an archive, a copy, a delete or a check before delete, when
  this PC's Archive / copy queue holds the entry as waiting, running or paused, when
  the Archive / copy tab works on it, and when the entry changed after the edit
  opened (D76). Check rows without a parent (the row of D2, Check archive, Compare
  with laptop copy) go with the entry. A question names the recording, its folder,
  start, channels, files and check rows, says that the files stay, and defaults to
  Cancel. Before the delete, a copy of the entry and its check rows is written to a
  new file `deleted-entries/recording-<id>-<UTC time>.json` next to the settings file;
  if that fails, nothing is deleted. One transaction then reads the entry and its
  rows again, refuses if they changed since the question, and deletes them. The form
  is cleared, the message names the copy, the Viewer refreshes, and the Archive /
  copy tab drops the recording from its form. A transfer whose recording was deleted
  meanwhile stops before it copies a file, because its first row needs the
  recording. When the deleted entry was the newest, the next new entry gets its
  number (D91).

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
  (fixed in code; DECISIONS.md D30). `*.txt` and `*.log` files at the top of the
  recording folder are side files, such as the recorder's logs; the result lists them
  with their sizes (D82). Other files, other subfolders, folders inside a channel
  folder and symbolic links are ignored and listed as "unrecognised" in the result.
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

## 8. Tab: Archive / copy

Milestone 5 builds the transfer core in `src/iqdm/transfer/` without a GUI. Milestone 6
builds the tab over it.

The app uses three terms for its transfers, in the code and on screen (D64). A
**copy** goes to a PC and leaves the recording entry unchanged. An **archive** goes to
the NAS, and the recording then points at it. A **delete** removes the laptop copy
after a passed archive. The app never moves files: an archive leaves the laptop copy
in place until the user deletes it.

### Operations

- **Copy to a local PC**: source is a recording (usually archived on the NAS). The
  recording entry is unchanged; a `transfer_log` row is added with `operation =
  'copy'`. The destination field starts with `default_local_copy_root` and the
  recording's relative path, which the user can change (D60).
- **Archive to the NAS**: source is a `local` recording on the laptop, whole,
  with all channels, and its folder must match the database entry (D50). Steps: copy,
  verify, then on success update `storage_root`, `rel_path`,
  `archive_state = 'archived'` and `archived_at` in the same transaction that
  finishes the `transfer_log` row. A failed verification leaves the recording `local`.
  If another archive pointed the recording elsewhere while this one ran, this archive
  is logged as failed, and the recording keeps the first archive copy. The preview
  warns when an archived recording has the same start, end and channel indices (D61).
- **Check before delete** (D55): reads the NAS files of a passed archive with the
  Windows file cache bypassed, and hashes them in the chosen hash mode. Each hash is
  compared with the copy-time hash in the manifest, or with a hash of the laptop file
  where the manifest holds none. Hash mode `none` is refused, because it reads no
  file content. It is logged as a `check` row with the archive in `parent_id`.
- **Delete the laptop copy**: a separate, explicit, user-confirmed action, offered
  only after an archive passed verification and a later check before delete passed
  (D55). It is logged as a `transfer_log` row with `operation = 'delete'` and the
  archive in `parent_id` (D52).
- **Compare with laptop copy** (D56): for an archived recording that was logged in
  place on the NAS (D2). The user picks the laptop folder. The app compares channels,
  file counts, sizes and SHA-256 in the chosen hash mode, and logs a `check` row with
  the laptop folder as `source` and the NAS folder as `destination`. A passed
  comparison clears the "not verified" mark. It does not allow deleting the laptop
  copy.
- **Check archive**: compare an archived recording's folder with its database entry:
  channels, and file count and total size per channel. It is logged with
  `operation = 'check'`. For a channel whose counts the database does not hold
  (legacy entries), the counts, sizes and times are taken from the folder: start from
  the first file, end from the last file plus the file duration. The recording's
  date, start and end follow its channels. That check is logged as `'skipped'`, and
  its note names a file spacing that differs from the stored file duration (D71). A
  folder that cannot be scanned is a failed check. Entries with counts keep their
  times.

Each copy or archive first writes its `transfer_log` row with `started_at`. A row with no
`finished_at` is a transfer that never completed, for example after a crash. A
cancelled transfer is finished with `verification = 'skipped'` and a note.

### Running, stopping and resuming

The tab (`gui/transfer_tab.py`, logic in `movecopy.py`) runs one operation at a time:
a preview, a copy, an archive, a check or a deletion. All run in a worker thread. The
queue (below) runs its items one after another, each as one such operation.

- **Locked form.** While an operation runs, the tab's inputs are locked. The Viewer
  and the Log tab stay usable. The Viewer's "Archive / copy" button opens no other
  recording until the operation ends. Settings Save waits for it.
- **Progress.** A copy shows a bar by bytes, files and bytes done, the speed over the
  last 10 s and the time left. A check shows bytes hashed and files checked. A
  deletion shows files deleted. A retry after an error shows the file, the attempt
  and the pause. The tab's title and the status bar show the running operation, for
  example "Archive / copy (copying 41 %)".
- **Run.** Run is enabled only after a preview that passed, and any change to the
  form drops the preview.
- **Stop.** Stop asks first for a copy or an archive (default No) and takes effect
  between chunks. Files already copied stay; the file being copied stays as
  `<name>.partial`. The row is finished as `skipped`, and its note says "Stopped after
  N of M files". A stopped check or deletion is logged as well. A check has no
  resume. A deletion run again finishes the rest.
- **Closing the window** during an operation asks first. Yes stops the operation and
  waits until its row is written.
- **Unfinished transfers.** The tab lists copies and archives that were stopped,
  failed or never finished, newest first in the order the rows were written (D74),
  for the current user or, on request, for
  all users. A later run of the same recording, destination, range and channels
  replaces an earlier one in the list. An archive leaves the list once its recording
  is archived. Open in form (named Resume before D86) fills in the form from the row
  and runs the preview; files
  already in place with the right size are not copied again (D51, D63). Forget asks
  first and sets `transfer_log.dismissed_at`; the row and the copied files stay.
- **Delete laptop copy** is enabled only when a check before delete of the current
  archive passed (D55). It asks first, names the folder, the file count and the size,
  and defaults to No.

### Queue

D81. `transferqueue.py` holds the queue and runs one item; it has no Qt.

- Items come from the Viewer ("Add to queue": "Archive or copy", or "Check archive")
  or from the form ("Add to queue" next to Run, after a passed preview). From the
  Viewer, a laptop recording is archived to the queue's NAS folder plus its relative
  path, and an archived one is copied to the default copy folder plus its relative
  path. Each item holds its own request; Edit takes it back into the form, and "Add
  to queue" puts it back in its place.
- An item that repeats an active item is refused: an archive or Check archive of the
  same recording, or any item to the same destination. Two copies of one recording to
  different folders are allowed.
- New archives and copies from the Viewer are previewed when added, if the tab is
  idle. Each is previewed again just before it runs; a preview with errors gives "Not
  started" and the queue moves on. A failed item does not stop the queue.
- After a passed archive, Check before delete runs when "After each archive, run Check
  before delete" is ticked (the default), except with "Sizes only". An archive that
  passed but whose check did not (failed, stopped, could not run, or skipped for
  "Sizes only") gets the state ⓘ "Archived, check needed" in amber, with a note that
  the recording points at the NAS copy and the laptop copy stays (D85). Clear
  finished keeps such items, Remove removes them, Start skips them, and the summary
  counts them apart.
- Pause asks first. It stops the running item between chunks, as Stop does. While a
  paused item waits, the Start button reads Resume; it continues the item, skipping
  the files already in place (D51, D63). A pause during Check before delete stops the
  check, and the item becomes "Archived, check needed".
- A paused or waiting item continues only in the queue (D86). The form's Run and Add
  to queue stay disabled while the queue holds a waiting, running or paused item that
  the form's transfer repeats, by the rule above; a line under the buttons says so.
  Remove frees the transfer for the form. The end of a queue run drops the form's
  preview.
- The queue lives in memory. Closing the window asks first while it runs or holds
  items that have not run.
- An item keeps the creation time of the entry it was made for. Before it runs, an
  item whose recording number now names another entry, or no entry, gets "Not
  started" with the reason (D91). A transfer checks its preview's entry the same way
  when it writes its first row, before any file is copied.

### Scope

- Whole recording, or a time range. A file at time `t` is in the range when
  `start <= t < end` (D49). Input is a date and time at the display offset, or Unix
  time, kept in sync (D59).
- Channel checkboxes: any subset of the recording's channels.
- Timeline showing the selected range against each channel's available data and gaps.

### Selection

`transfer/selection.py`. Before every transfer the app rescans the source folder with
the scanner (D53). The rescan gives the real file names, the size of each file and the
gaps. The selection holds, per channel, the files in the range, their total size and
the missing seconds inside the range (D49). It also lists where the folder differs
from the database entry. Every selection also holds the side files, the `*.txt` and
`*.log` files at the top of the recording folder such as the recorder's logs,
whatever its channels and range (D83). They are copied, checked, listed in the
manifest and, after an archive, deleted with the laptop copy like data files; the
transfer's file count and size include them. Check archive and Compare with laptop
copy compare the channels only.

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
  files at once. The app copies `copy_workers` files at once (D58).
- A dry run is the preview: it computes the selection, the destination checks and the
  estimate, and writes nothing.
- `transfer/power.py` keeps Windows from sleeping while a transfer runs.

### Manifest

After each copy or archive that passes verification, the app writes a manifest (D52): a
JSON file in the `manifests` folder next to the configuration file, named
`transfer-<id>-<finish time>.json`, for example `transfer-7-20261003T080000Z.json`.
It lists each file's relative path (`/`-separated), size and SHA-256 where one was
computed, with the transfer's source, destination, range and channels. It is written
only to a new file. An archive's destination is stored as its NAS location, with a mapped
drive letter replaced by the UNC path (D14), so the log row, the manifest and the
recording name the same folder. `transfer_log.manifest_path` holds its path and
`transfer_log.manifest_sha256` the SHA-256 of its bytes.

### Transfer safety

- **Destination validation** (`transfer/pathcheck.py`): not a drive root or a share
  root, not equal to or inside the source, source not inside the destination. Paths
  compare without letter case. An archive needs a destination that is new, empty, or
  holds only the target files of an interrupted archive of the same selection. A copy
  also accepts a destination that holds other files (D51). Free space must cover the
  bytes still to copy plus `free_space_margin_gb`. Paths must stay within the Windows
  limits (259 characters for a file, 247 for a folder) unless long paths are enabled.
  An archive destination must lie under a NAS root, at a location no other recording
  uses (D50). Besides the path text, the checks compare file identity, so a folder
  reached under two names counts as one folder: the destination and the source
  folder, the folders above them, and each target file already in place and its
  source file (D75).
- **Preview** before running: file count, total size, missing seconds per channel,
  estimated time from `network_speed_mb_s` and for the chosen hash mode, the
  destination checks, and the file list.
- **Verification** (`transfer/verify.py`): always compare the count and each file's
  size between the selection and the destination. Optional SHA-256 by `hash_mode`:
  `none`; `sample`, which hashes `ceil(hash_sample_fraction × n)` files, at least one,
  chosen as the files whose relative path has the smallest SHA-256; or `all`. Source
  hashes come from the copy where it computed them. When the hash mode is not `none`,
  every file the copy skipped as already in place is also hashed on both sides (D63).
  Files in the destination that are not in the selection are reported and do not
  fail the verification. A destination file that is the source file under another
  name fails it (D75).
- **Deletion**: all deletion goes through `src/iqdm/transfer/delete.py` (D52). It
  needs an archive with a passed verification, a manifest whose SHA-256 matches, and
  a passed check before delete of that archive, written after it (D55; D74 compares
  the order of the rows, not the PCs' clocks). The
  recording must point at the archive's destination. Right before each source file is
  deleted, its destination copy and the source file must still have the manifest
  size, and they must be two different files. A file whose identity cannot be read is
  kept (D75). It deletes only the files in the manifest, never whole trees by pattern, and
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
    KICKOFF.md                # the first message of each new session: ready and template prompts
    KICKOFF_ARCHIVE.md        # earlier session prompts, kept as a record
    HANDOFF.md                # current state, outstanding items, how to proceed
    USER_GUIDE.md             # short guide for users, shipped in the build folder
    RELEASE_NOTES.md          # what each release does and its known limits, shipped too
    mockup/                   # exported GUI mockups
  src/iqdm/
    __main__.py               # python -m iqdm
    app.py                    # QApplication, main window and its tabs, --config/--db
    config.py                 # TOML config load and save (Settings tab, D31), defaults
    models.py                 # dataclasses: Recording, Channel, Param, TransferEntry...
    timeutil.py               # UTC ISO 8601 text <-> Unix seconds; display offset (D24)
    location.py               # folder -> storage_root, rel_path, archive state (D14)
    entry.py                  # Log tab logic: form input, checklist, save (no Qt)
    bands.py                  # the band list and the band of an fc (D88)
    deletion_record.py        # the copy of a deleted entry, written once (D89)
    batchlog.py               # several folders with one set-up: forms, checklists, saves (D90)
    viewer.py                 # Viewer logic: filters, table text, details, gap lines (no Qt)
    movecopy.py               # Archive / copy tab logic: time input, preview text, states (no Qt)
    legacy.py                 # legacy import: folder rules, grouping, report (D66; no Qt, no SQL)
    db/
      schema.sql
      version.py              # LATEST_VERSION and schema_status(), shared by the two below
      connection.py           # connect(), read-only connect, retry-on-lock helper
      migrations.py           # user_version-based migrations, backup before migrate
      repository.py           # all queries and writes
      legacy.py               # reads the legacy table read-only; writes the import (D66)
    scan/
      scanner.py
    transfer/
      selection.py            # rescan + range + channels -> file list, gaps (D53)
      pathcheck.py            # destination validation
      manifest.py             # per-file manifest, written once (D52)
      copier.py               # the copy engine (D48)
      verify.py               # count/size/hash verification
      uncached.py             # reads files past the PC's file cache (check before delete, D55)
      delete.py               # the only module that deletes files
      estimate.py             # size/time estimates
      operations.py           # copy, archive, check and delete flows with their log rows
      power.py                # keeps Windows awake during a transfer
    diagnostics/              # copy check, database check and NAS test set (D57)
    check_main.py             # console program IQDataManager-check.exe (D57)
    gui/
      viewer_tab.py
      log_tab.py
      transfer_tab.py
      settings_tab.py         # Settings tab (section 4, D29)
      workers.py              # QThread/QRunnable wrappers
      widgets/                # timeline, checklist, param table, recordings table model
  tools/                      # thin wrappers over iqdm.diagnostics from Milestone 6 (D57)
    make_fixtures.py          # synthetic IQ recordings for tests and manual testing
    db_check.py               # create, write and locking checks on a scratch database (O21)
    copy_check.py             # copy-engine throughput, flush on and off (D48, D54)
    make_nas_testset.py       # synthetic recordings for the NAS field test (D54)
    migrate_legacy.py         # legacy DB -> new schema (writes a NEW file; D66)
  tests/
  build/
    iqdm.spec                 # PyInstaller spec: IQDataManager.exe and IQDataManager-check.exe
    defaults.example.toml     # template of the defaults file, example values only (D68)
```

GUI rule: the mouse wheel never changes a dropdown or a number field. An event filter
on the application (`gui/widgets/wheel_guard.py`, installed by the main window) keeps
wheel events from every `QComboBox` and `QAbstractSpinBox` and passes them to the
parent, so the page scrolls (D92).

Rules: nothing outside `gui/` and `app.py` imports PySide6. All SQL lives in `db/`,
and only `db/` imports `sqlite3` (DECISIONS.md D7). `transfer/delete.py` is the only
place that deletes files.

## 10. Legacy data migration

The current database has one table with columns `date, date_unix, site, band, fc_hz,
fs_hz, duration_s, data_dir, remarks`. `date` is text at UTC+8 with a day only, such
as `12-Apr-2023`; `date_unix` always wins over it, and also gives the day only (D71). `fc_hz` and `fs_hz` are in Hz, `duration_s` in whole seconds. Each
channel of a multi-channel capture is a separate row whose `data_dir` ends in the
channel folder, for example `\\192.168.1.50\Data\IQ\recording1\0\` (D66).

`IQDataManager-check.exe migrate-legacy LEGACY_DB NEW_DB --nas-root UNC [--nas-root
UNC ...] [--drive Z:=UNC ...] [--table NAME] [--dry-run]` reads a copy of the legacy
file read-only and writes a new database file; it never modifies the original. It
refuses a `NEW_DB` that exists. `tools/migrate_legacy.py` runs the same code (D57).

Mapping (D66):

- A last folder named by a canonical decimal number (D11) is a channel folder: it gives
  `channel_index` and `sub_path`, and its parent is the recording folder. Any other
  `data_dir` is the recording folder, with channel 0.
- The recording folder is split into `storage_root` and `rel_path` by D14, using the
  `--nas-root` UNC roots and the `--drive` letter-to-UNC mapping.
- Rows with the same recording folder, compared without letter case, become one
  recording. A repeated channel index, a mix of channel folders and the bare folder,
  or two sites in one group send the group to the report. Different remarks are
  joined with " | ".
- Each row becomes one channel (`band`, `fc_hz`, `fs_hz`, `start_unix = date_unix`,
  `end_unix = date_unix + duration_s`, `n_files` and `total_bytes` NULL).
- Distinct `site` values, compared without letter case, become `sites` rows.
- Each recording gets `archive_state = 'archived'`, `logged_by = 'legacy-import'`,
  the format defaults (`int16`, interleaved I/Q, little-endian, no header,
  1 s files) and the in-place row of D2, so it shows "archived, not verified".
- A `date` that cannot be read gives a warning. So does a `date` with a time more than
  1 s from `date_unix`, and a `date` with a day only when `date_unix`, read at UTC+8,
  falls on another day (D71).
- Rows that cannot be mapped are written to a report, not guessed. A real run writes
  the report as `<NEW_DB>.report.txt`; a dry run only prints it. All recordings are
  written in one transaction.

A later "Check archive" on each imported recording fills in counts and sizes, and
takes each channel's start and end from its files (D71).

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
   verification, delete module, and the copy, archive, check and delete flows with
   their `transfer_log` rows. No GUI. Heavily tested.
6. **Archive / copy tab**: GUI over the core, preview, run with progress and cancel,
   post-verification delete flow, the transfer keys in the Settings tab. The
   Viewer's "Archive / copy" button comes with this tab (D42). The milestone starts
   with the change of term from "move" to "archive" (D64), and ends with the first
   test on the NAS, with the test set from `tools/make_nas_testset.py` (D54).
7. **Packaging and migration**: PyInstaller build, legacy migration tool (packaged, so
   it runs without Python; D66), "New database..." in the Settings tab (D67, in place
   of the admin option `--create-db PATH` that D30 planned), the defaults file in the
   program folder (D68), long paths in the packaged app (D65), short user guide. The
   settings dialog and the config writer moved to Milestone 3a (D29).
8. **Release 1.0** (D72): the second test on the NAS (locking between two PCs, O21;
   Check before delete past the PC's cache, D55; the legacy import of real data with
   Check archive, in a trial catalogue), the version 1 schema frozen when the real
   catalogue is created (O20), version 1.0.0, a final build from `main` and release
   notes. Recommended before rollout: a backup of the catalogue (O22), a pilot on one
   real recording, and the team's `defaults.toml`.

Milestone 8 closed on 2026-10-12 with version 1.0.0; O20 and the rollout moved to the
open items and the user. Later work takes its scope from the open items in
`docs/STATUS.md`, one piece of work per branch, each with a report, as
`docs/HANDOFF.md` describes. A new feature or a change of the database format is
specified here first, with its decision.

## 13. Scope

Out of scope for v1: Linux build, transfer scripts (D48), file-level gap storage in
the DB, user accounts, editing RF chain templates. Deleting a catalogue entry with an
archive, a copy or a delete in its history (D89; D41 kept every delete out of the GUI
until version 1.2).

Open questions and assumptions that may still change are listed in `docs/STATUS.md`.
Resolved decisions are in `docs/DECISIONS.md`.
