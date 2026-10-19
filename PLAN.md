# Plan scratchpad

This file is a scratchpad for the current agent's plan. Any later agent may replace
it with its own plan. It is not a requirement: decisions go in `docs/DECISIONS.md`,
requirements in `docs/SPEC.md`, and open items in `docs/STATUS.md`. The safety hook
blocks plan files outside the repository, so plans are written here.

Current plan: version 1.1. Written 2026-10-20. Status: approved by the user on
2026-10-20. The user gave no answer to the three questions at the end, so the plan's
defaults apply until the user says otherwise.

## Context

The team gave feedback after release 1.0.0 and a passed pilot. Each new Log tab entry
needs its format, channel and RF chain fields typed again, because D26 resets them for
each new folder. The Archive / copy tab runs one transfer at a time, so each archive
has to wait for the one before it. Version 1.1 adds field carry-over and template
files to the Log tab, and a queue to the Archive / copy tab. It also includes O38
(Viewer filters that take several choices), O41 (Check archive for many recordings,
through the queue) and O20 (the frozen version 1 schema).

None of the planned work changes `schema.sql`. Templates are files and the queue is
held in memory. O20 still goes first, as HANDOFF.md section 5 asks.

## The user's answers so far (2026-10-20)

- The pilot passed: D75 on the NAS, the pilot archive, Check before delete and the
  delete. "All passed" is read to include D76 across two PCs. The user is asked to
  correct this if D76 across two PCs was not tested.
- O38, O20 and O41 join 1.1. O42 closes as not needed: no antivirus or SmartScreen
  block was seen.
- Templates are files. Pause stops the running item safely, and Start resumes it.
- A template can hold any field the user types, site and project included. Values
  from the scan stay out. Every field is optional, and export lets the user choose
  the fields to save.
- Viewer multi-select adds items to the queue. The user asked how per-item settings
  work. Section 5, "Per-item settings", answers that question.

## Proposed open items (not in STATUS.md until the user approves)

| ID | Item | When | Proposed default | Origin |
| --- | --- | --- | --- | --- |
| O43 | A new Log tab entry keeps the fields of the previous one. Only the values that come from the scan are reset. | 1.1.0 | Keep logged by, site, project, plan reference, remarks, sample type, IQ layout, endianness, header bytes, band and fc per channel number, and the RF chain rows. Reset start and end, file counts, fs (filled in again from the scan, D21) and file duration (set again from the file names, D22). A note in the "Before saving" panel lists the kept format values. Clear form still resets everything. Replaces D26. | User, 2026-10-20 |
| O44 | Import and export a Log tab template file, for example for common hardware set-ups | 1.1.0 | A TOML file that can hold every field the user types: logged by, site, project, plan reference, remarks, sample type, IQ layout, endianness, header bytes, band and fc per channel number, and the RF chain rows. Values that come from the scan are never in it: start and end, file counts, fs, file duration, storage root, relative path and archive state. Every field is optional. Export asks which fields to save. Import changes only the fields the file holds and leaves the others as they are. | User, 2026-10-20 |
| O45 | A queue in the Archive / copy tab: add several archives and copies, then Start; Pause pauses the whole queue | 1.1.0 | Section 5 below. O41 joins it as a Check archive queue item. | User, 2026-10-20 |

## Current behaviour, by item

**O20.** `tests/schemas/` does not exist. `schema.sql` has not changed since `v1.0.0`
(`git diff v1.0.0 HEAD -- src/iqdm/db/schema.sql` is empty). `LATEST_VERSION` is 1
(`src/iqdm/db/migrations.py`, `upgrade()` at line 128).

**O38.** `RecordingFilter` holds one `site_id`, one `project_id`, `without_project`
and one `band` (`src/iqdm/models.py:159-177`). `_filter_sql()` uses `=` and refuses a
project together with "no project" (`src/iqdm/db/repository.py:560-600`).
`viewer.parse_filter()` builds the filter (`src/iqdm/viewer.py:85-104`). The Viewer has
three single-choice `QComboBox` filters (`src/iqdm/gui/viewer_tab.py:174-176`, filled
at 486-504, read at 575-582).

**O43.** `_folder_changed()` (`src/iqdm/gui/log_tab.py:510-526`) runs on every change
to the folder text, including each keystroke. It calls `_reset_folder_fields()`
(474-488), which resets the duration, the four format fields, the channel rows and
the RF chain rows. Logged by, site, project, plan reference and remarks stay. After a
save nothing resets (`_saved_new`, 986-1002). `_set_channel_rows()` (559-605) already
reuses typed band, fc and fs by channel number. The folder change empties those values
before the scan, so nothing is reused. An RF chain row for a channel that is not in the
scan is an error (`entry._param_items`, `src/iqdm/entry.py:674-680`). Before a scan
the channel list is empty, so every kept channel row would show as an error.

**O44.** No template code exists. `config.py` reads TOML with `tomllib`
(`read_config_data`, 212-221) and writes it with `tomli_w` through a `.new` file and
`Path.replace` (`save_config`, 398-424). The Settings tab already uses
`QFileDialog.getSaveFileName` (`settings_tab.py:762-773`).

**O45 and O41.** The tab calls `operations.preview_transfer` and `run_transfer`
directly (`transfer_tab.py:59-73`, 880-1005). Run needs a passed preview of the
current form (1492-1497). Stop sets the `Task` cancel event, and the copier checks it
between 8 MiB chunks (`copier.py:231`, 308). A stopped run is finished as `skipped`
with "Stopped after N of M files" (`operations.py:386-390`). While anything runs,
the whole form is locked (`_update_buttons`, 1456-1518). An archive destination has
no default: the user browses to a folder under a NAS root (671-686, 864-874). A copy
destination defaults to `default_local_copy_root` plus `rel_path` (D60). The Viewer
table allows one selection (`viewer_tab.py:261`). Settings Save and the Viewer's
Archive / copy button refuse while the tab is busy (`app.py:201-208`, 229-235). There
is no pause anywhere in the code.

## 1. Branch `o20-freeze-schema-v1`

- `tests/schemas/v1.sql`: the bytes of `git show v1.0.0:src/iqdm/db/schema.sql`,
  written with the Write tool.
- `tests/test_schema_freeze.py`:
  - A database built from `v1.sql` and taken through `migrations.upgrade()` has the
    same tables, columns, indexes and triggers as one built from the current
    `schema.sql`. The comparison reads `sqlite_master` and `PRAGMA table_info`.
  - While `LATEST_VERSION` is 1, `schema.sql` equals `v1.sql` apart from line
    endings. An edit in place then fails a test.
- Docs: D77 "Version 1 schema frozen". HANDOFF.md section 5 and STATUS.md: O20
  closed, and the pending checks closed after the pilot.

## 2. Branch `viewer-multi-filter` (O38)

The proposed default from STATUS.md.

- `models.RecordingFilter`: `site_ids`, `project_ids` and `bands` become tuples, and
  `without_project` stays. An empty tuple means all.
- `repository._filter_sql()`: `IN (?, ...)`. Projects and "no project" combine with
  OR. Bands go into the same channel `EXISTS` with the fc range, with `COLLATE
  NOCASE` (D43).
- `viewer.FilterInput` and `parse_filter()` take the tuples.
- `gui/widgets/check_combo.py` (new): a drop-down list with a checkbox per entry. Its
  text reads "All sites" or a list of the ticked names. The Viewer uses it for site,
  project ("No project" is one entry) and band.
- Every caller of `RecordingFilter(site_id=...)` changes too. A Grep finds them.
- Tests:
  - `test_repository.py`: several sites; several projects; projects with "no
    project"; several bands with an fc range on one channel; an empty tuple matches
    all.
  - `test_viewer.py`: `parse_filter` with the tuples.
  - `test_viewer_tab.py`: ticking two sites shows both; nothing ticked shows all.
  - `test_user_text.py`: the new widget's texts.
- Docs: D78 amends D43 and the Viewer part of D73. Updates SPEC section 5 and
  USER_GUIDE section 4.

## 3. Branch `log-keep-fields` (O43)

- `gui/log_tab.py`:
  - `_folder_changed()` resets only what the scan gives: `_clear_scan()`, the
    duration flags, and the fs values filled in from the scan. It keeps format,
    band, fc and RF chain rows. A new `_carried: dict[int, ChannelInput]` keeps band
    and fc by channel number, so they survive an empty channel table until the next
    scan fills it.
  - `_reset_folder_fields()` is renamed `_reset_all_fields()` and is called only by
    `clear_form()`.
  - After a scan, channel-scoped RF chain rows for channels that are not in the new
    folder are removed. The message line names them, as D20 does in edit mode.
  - A new `kept_note` label in the side panel, for example: "Kept from the previous
    entry: int8, interleaved_iq, little, header 0 bytes, 2 channel settings, 5 RF
    chain rows. Check them for this folder." It shows only in a new entry whose
    values came from an earlier folder. It hides after Clear form and in edit mode.
- `entry.py`: `_param_items` no longer reports "channel X is not in this recording"
  while a new entry has no scan. "Scan the folder" is already a to-do item then.
- Tests in `test_log_tab.py`:
  - Rewrite `test_new_folder_resets_format_channels_and_rf_chain` as
    `test_new_folder_keeps_format_channels_and_rf_chain`.
  - fs is filled in again for the kept sample type.
  - The duration comes from the new file names.
  - Channel 2 rows are removed when the new folder has channels 0 and 1, and the
    message names them.
  - Band and fc carry over by channel number.
  - The note shows, and it hides after Clear form.
  - Typing in the folder field does not clear the RF chain.
  - Edit mode is unchanged.
  - `test_user_text.py` covers the note.
- Docs: D79 replaces D26. D26's status becomes "Replaced by D79". The D79 entry
  records the risk D26 fixed (int8 carried over gives the wrong fs) and the remedy
  (the note names the kept sample type). Updates SPEC section 6 ("Choosing another
  folder...") and USER_GUIDE section 3.

## 4. Branch `log-templates` (O44), after `log-keep-fields`

### What a template holds

- Any field the user types:
  - **Recording group:** logged by, site, project, plan reference and remarks.
  - **File format:** sample type, IQ layout, endianness and header bytes.
  - **Channels:** band and fc per channel number.
  - **RF chain:** its rows.
- Never a value from the scan: start and end, file counts, fs, file duration,
  storage root, relative path or archive state. Those fields stay empty until a
  scan fills them, as in O43.
- Every field is optional. A template may hold one field or all of them. Import
  changes only the fields the file holds.
- Site and project are stored by name, because ids differ between catalogues. On
  import, a name is matched without letter case against the catalogue. A name the
  catalogue does not hold is not added: the field stays as it was, and the message
  line names the missing site or project, so the user can choose it or use Add
  site.

### Changes by file

- `src/iqdm/templates.py` (new, no Qt):
  - `TemplateField`, an enum of the groups the user can choose on export: logged
    by, site, project, plan reference, remarks, file format, channels, RF chain.
  - `LogTemplate` dataclass. Every attribute is optional, and None means "not in the
    template".
  - `template_from_input(EntryInput, names, fields)` builds a template from the
    form, holding only the chosen fields. `names` turns site and project ids into
    names.
  - `apply_template(EntryInput, LogTemplate, choices) -> (EntryInput, notes)`
    changes only the fields present. `choices` resolves site and project names to
    ids. `notes` lists names that were not found.
  - `read_template(path)`: `tomllib`, with `format_version = 1`, enum and number
    checks, and `TemplateError` with plain text. A file without any known field is
    an error. A key the app does not know is an error, so a misspelt key is not
    ignored without a word.
  - `write_template(path, template)`: `tomli_w` to `<name>.new`, a read-back check,
    then `Path.replace`. This follows `config.save_config`. It keeps no `.bak`.
- Example of a file with every group:
  ```toml
  format_version = 1
  logged_by = "perry"
  site = "Rooftop A"
  project = "Survey 2026"
  recording_plan_ref = "RP-12"
  remarks = "Standard USRP set-up"
  sample_type = "int16"
  iq_layout = "interleaved_iq"
  endianness = "little"
  header_bytes = 0
  [[channels]]
  index = 0
  band = "VHF"
  fc_mhz = "145.8"
  [[rf_chain]]
  applies_to = "recording"   # or a channel number
  param = "SDR"
  value = "USRP B210"
  unit = ""
  ```
  A file with only `format_version` and the `[[rf_chain]]` rows is also valid.
- `gui/log_tab.py`:
  - "Import template..." and "Export template..." buttons in the side panel.
  - Export opens a small dialog with one checkbox per field group. Each box shows
    the current value or a count, for example "RF chain (5 rows)". The boxes for
    empty fields start unticked, and the others start ticked. The file dialog
    follows.
  - The file dialogs start in the last folder used, which is kept in `QSettings`
    for the user and is not a config key.
  - Import changes only the fields the file holds. Band and fc go through
    `_carried` by channel number, so import also works before a scan. RF chain
    rows in the file replace the form's rows. A file without RF chain rows leaves
    the form's rows as they are.
  - After an import, the message line says which field groups were set and names
    any site or project that was not found.
  - In edit mode, D16 still applies: a change to sample type or header needs a
    rescan.
  - Errors appear on the message line.
- `gui/widgets/template_fields.py` (new): the export dialog.
- Tests:
  - `tests/test_templates.py`:
    - a round trip with every field, and with each field group alone;
    - export of only the chosen fields;
    - import leaves the fields the file does not hold unchanged;
    - site and project by name without letter case, and a missing name gives a
      note and no change;
    - a bad version, a bad enum, a bad number, an unknown key, and a file with no
      known field;
    - channel rows for channels the scan does not hold;
    - export over an existing template file under `tmp_path`.
  - `test_log_tab.py`:
    - import before and after a scan;
    - export of some fields, then import into a cleared form, sets only those
      fields;
    - export, then import, gives the same form;
    - the export dialog starts with the boxes for empty fields unticked.
  - `test_user_text.py`: the dialog and message texts.
- Docs: D80. SPEC section 6 and a new section 4 line saying the file is not
  configuration. USER_GUIDE section 3.
- Code paths that overwrite a file: `write_template` replaces a template file the user
  chose, after Qt's overwrite question. The report lists it.

## 5. Branch `transfer-queue` (O45, O41)

### What the user sees

A new "Queue" group in the Archive / copy tab has these parts:

- a table with one row per item: recording, operation, channels and range,
  destination, size, and state. The states are Waiting, Checking, Copying, Done,
  Failed, Not started (with the reason) and Paused;
- a "NAS folder for archives" field with Browse;
- an "After each archive, check it for delete" checkbox, ticked by default;
- the buttons Start, Pause, Edit, Remove and Clear finished.

Items can be added in two ways:

1. **Viewer.** The recordings table allows several selections. A new "Add to queue"
   button holds a menu with two choices:
   - **Archive or copy.** A local recording becomes an archive to `<NAS folder for
     archives>\<rel_path>`. An archived recording becomes a copy to the default copy
     folder plus `rel_path` (D60). Both are whole recordings with all channels and
     the queue's check mode.
   - **Check archive** (O41). Only archived recordings can be added this way.

   Edit entry, Archive / copy, Scan for gaps and Open folder need exactly one
   selected recording.
2. **The tab's form.** Load a recording as today and set its operation, channels,
   time range, destination and check mode. Then click "Add to queue", which sits
   next to Run.

### Per-item settings

These answer the user's question about rec1, rec2, rec3 and different NAS locations.

- Each queue item holds a full `TransferRequest`, with its own operation,
  destination, channels, range and check mode.
- **Edit** takes an item out of the queue and loads it into the form. Change
  anything there, Preview, then "Add to queue" puts it back in the same place.
- So rec1 can copy channel 0 only, rec2 channels 0 and 1, and rec3 a time range. Add
  all three from the Viewer, then Edit each one. Or set each in the form and click
  "Add to queue".
- Different NAS locations work the same way: Edit the item and change its
  destination.
- **Limit:** an archive is always the whole recording with all channels (D50).
  Channel and range choices apply to copies only. The form already enforces this
  rule.

### Running

- An item is previewed when it is added, if the tab is idle. The preview shows its
  size and any problem.
- Each item is previewed again just before it runs. That preview rescans the source
  (D53) and checks the destination and the free space at that moment. A failed
  preview marks the item "Not started: <reason>", and the queue moves on.
- A failed archive or copy is marked Failed, and the queue moves on.
- With the checkbox ticked, a passed archive is followed by Check before delete in
  the item's check mode. "Sizes only" skips the check and says why.
- Delete laptop copy stays a separate action for one recording, which asks first.
- **Pause** asks first, with default No, as Stop does. It cancels the running step
  between chunks. Copied files stay, and the item becomes Paused. Its log row is
  finished as `skipped`, as today. Start continues with that item: the new preview
  finds the files already in place and skips them (D51, D63).
- While the queue runs:
  - the form, the Checks buttons and Run stay locked, as today;
  - Waiting items can be removed;
  - more items can be added from the Viewer. They are previewed just before they
    run.
- The queue lives in memory. Closing the window with a running or waiting queue
  asks first. A paused or stopped item remains under "Unfinished transfers", as
  today.

### Changes by file

- `src/iqdm/transferqueue.py` (new, no Qt):
  - `QueueItem` and `ItemState` dataclasses.
  - `TransferQueue` with add, remove, next waiting item, take out for edit and put
    back, and refusal of a duplicate (same recording and operation already waiting,
    or same destination).
  - `item_from_recording(rec, kind, nas_folder, config)`.
  - `run_item(db, item, config, ..., cancelled) -> ItemResult`, which calls
    `preview_transfer`, `run_transfer` and, if wanted, `check_before_delete`, or
    `check_archive` for O41. It holds no file code of its own.
- `gui/transfer_tab.py`:
  - the Queue group and an "Add to queue" button;
  - a loop on the main thread that starts one `Task` per item through the existing
    `TaskRunner`;
  - `is_busy` is also true while the queue runs, so Settings Save and the Viewer's
    button still wait;
  - Pause reuses `stop()`;
  - progress text such as "Archive / copy (queue 2 of 5, copying 41 %)".
- `gui/viewer_tab.py`: `ExtendedSelection`; the "Add to queue" menu; single-selection
  actions are enabled only for one row; the details show the current row.
- `app.py`: wiring between the Viewer and the tab, and the close question.
- `movecopy.py`: text helpers for queue states.

### Tests

- `tests/test_transferqueue.py`:
  - add, remove and refuse a duplicate;
  - default destinations for an archive and a copy;
  - `run_item` for archive with check, copy, and check archive, under `tmp_path`;
  - a cancelled `run_item` leaves `.partial` files and a `skipped` row, and the next
    `run_item` skips the copied files and passes;
  - a failed preview gives "Not started".
- `tests/test_transfer_tab.py`:
  - add from the form;
  - Start runs three items in turn;
  - Pause, then Start, completes the paused item;
  - removing a waiting item while the queue runs;
  - a failed item does not stop the queue;
  - Edit puts an item back in the same place;
  - `is_busy` while the queue runs.
- `tests/test_viewer_tab.py`: multi-select; "Add to queue" emits the ids;
  single-row actions are disabled for two rows.
- `tests/test_app_smoke.py`: the close question with a waiting queue.
- `tests/test_user_text.py`: the queue texts.

### Docs

- D81: the queue. It records that pause is stop-and-resume, and why the queue is not
  saved to disk.
- SPEC section 8: a new subsection "Queue". "Running, stopping and resuming" changes
  to "one operation at a time, or a queue run in turn". SPEC section 5 covers the
  multi-select.
- USER_GUIDE section 5: a new subsection "Queue". USER_GUIDE section 4 covers the
  Add to queue button.
- O41 closes with D81.
- Code paths: no new code copies, renames or deletes. The queue calls `run_transfer`,
  `check_before_delete` and `check_archive` unchanged. The report states this, and
  `test_architecture.py` still passes.

## 6. Release 1.1.0, after the user approves each merge

Branch `release-1.1.0`. It sets `__version__ = "1.1.0"` and adds RELEASE_NOTES 1.1.0
in plain words. Then follow HANDOFF.md section 4: build into
`dist/release-1.1.0`, run the checks, and tag and push with approval. The real
catalogue needs no upgrade.

## Each branch, before it is done

- `pytest` and `ruff check` pass (1,607 passed and 4 skipped at the start).
- A report `docs/reports/2026-10-<dd>-<topic>.md` follows REPORT_TEMPLATE.md.
- STATUS.md: the item is closed, and the "not tested" items are recorded.
- Offscreen screenshots in light and dark palettes under `dev/`, which the user
  removes later.
- Every new string is read as a user would read it.
- Not testable here: the queue against the real NAS, and a pause across a long
  network outage. Both are left to the user with the 1.1 build.

## Questions still open

1. O43: should channel rows for channels that are not in the next folder be removed
   after the scan, as planned? Or should they be kept as hidden values that come back
   for a later folder that has that channel?
2. O44: on import, should a site or project name the catalogue does not hold be
   added to the catalogue? The plan does not add it: it names the missing value
   and leaves the field unchanged.
3. O45: should the queue be saved to a file next to the configuration, so it survives
   a restart? The plan keeps it in memory for 1.1.
