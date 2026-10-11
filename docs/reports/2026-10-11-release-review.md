# Release review before 1.0

| | |
| --- | --- |
| Branch | `m8-release`, reviewed at `e6f0569` |
| Tests | 1,570 passed, 4 skipped (`pytest`); `ruff check` clean |
| Build | `dist/review-1/IQDataManager/`, from `e6f0569` |
| Report date | 2026-10-11 |
| Merge status | Not merged. This report is phase 1 of the review: no code, test or document was changed. |

The review followed the prompt in [KICKOFF.md](../KICKOFF.md), "Release review". It
covers data safety, the database, transfers, the GUI, the legacy import, packaging,
the documents and the visible text. Known items are not findings here: O19, O20, O22
and O37 in [STATUS.md](../STATUS.md), the version 0.1.0, and D73 not yet tried by eye.

## Summary

Two findings are blockers for 1.0. Both can damage the real catalogue or the only
copy of a recording, and both were reproduced on synthetic data.

1. **The same folder under two names passes every check, and Delete laptop copy then
   deletes the only copy** (finding 1).
2. **A Log tab edit saved after an archive puts the recording back on the laptop**
   (finding 2).

One finding should be fixed (finding 3). Thirteen findings are minor.

Recommendation: do not release 1.0 at `e6f0569`. Fix findings 1 and 2, which are
small and testable here, then build again and repeat the checks of this report.

## Checks run

| Check | Result |
| --- | --- |
| `pytest` | 1,570 passed, 4 skipped in 121.35 s. Three skips need the symbolic-link privilege ([test_delete.py](../../tests/test_delete.py), [test_pathcheck.py](../../tests/test_pathcheck.py), [test_scanner.py](../../tests/test_scanner.py)); one runs only off Windows ([test_location.py](../../tests/test_location.py)). |
| `ruff check` | "All checks passed!" |
| Build with the README commands into `dist/review-1` and `build/work-review-1` | Exit code 0; log in `build/review-1-build.log`. The program folder is 104 MB. |
| `IQDataManager.exe --smoke-test` | Exit code 0 |
| `IQDataManager-check.exe --help` and `--version` | Exit code 0; the four commands listed; version 0.1.0 |
| `longPathAware` check (README, "Build") | `true` in both executables |
| Files next to the programs | `USER_GUIDE.md`, `FIELD_TEST_CHECKLIST.html` and `defaults.example.toml`, each byte for byte equal to its source |
| README commands that change nothing | `python -m iqdm --smoke-test` exit 0; `python -m iqdm --version` prints 0.1.0; `--help` of the five scripts in `tools/` exit 0 |
| Reproductions | `dev/review/test_review_repro.py`: 4 tests, all passed, under `tmp_path` with synthetic recordings from `make_fixtures`. They confirm findings 1, 2, 3 and 11. `dev/` is gitignored, so the file is not committed. |
| Offscreen screenshots | `dev/review/shots.py` rendered the four tabs in a light and a dark palette into `dev/review/shots/`, with a scratch database that holds one recording with a project |

One shell command was blocked by the safety hook. A `grep` over `src/` for file-writing
calls had the word `rmdir` in its pattern. The same search ran with the Grep tool, as
"Notes for agents" in STATUS.md says.

## Findings

Severity: **blocker** for 1.0, **should fix**, or **minor**.

### 1. Blocker: the same folder under two names loses the only copy

- **Where:** [pathcheck.py:107-119](../../src/iqdm/transfer/pathcheck.py#L107-L119)
  (`_path_errors`) and [delete.py:177-187](../../src/iqdm/transfer/delete.py#L177-L187)
  (`_keep_reason`).
- **What is wrong:** the check that the destination is "not equal to or inside the
  source" (CLAUDE.md; SPEC section 8, "Transfer safety") compares path text only. No
  code compares file identity (`os.path.samefile` or the file ID). Two names of one
  folder therefore count as two folders. The delete checks also compare only that
  the NAS file exists with its manifest size, right before the laptop file is
  deleted.
- **Failure:** a NAS folder is reachable as `\\nas01\recordings\X` and as
  `\\192.168.1.50\recordings\X`, and `nas_roots` holds only the second. A user logs
  the first name. The Log tab says "The folder is on a network share outside the
  configured NAS roots, so it is logged as local." The user then archives the
  recording to the second name, which is the same folder. The preview lists every file
  as "already in the destination with the right size". The archive copies nothing,
  and its verification hashes each file against itself and passes. Check before
  delete passes for the same reason. Delete laptop copy then deletes every file. The
  recording points at the NAS folder, which is now empty. A mapped drive whose UNC
  path uses another host name than `nas_roots` leads to the same result, because D14
  replaces the drive letter with the drive's own UNC path.
- **Confirmed by:** `test_finding_1_same_folder_under_two_names_loses_the_only_copy`
  in `dev/review/test_review_repro.py`. A directory junction under `tmp_path` gave the
  laptop folder a second name under the NAS root. The preview passed with all 12
  files in `existing`, the archive passed with 0 files copied, the check before
  delete passed, and the delete removed all 12 files. No copy of any file remained.
  The preview also states "Destination checked: … outside the source"
  ([movecopy.py:265-271](../../src/iqdm/movecopy.py#L265-L271)), which was false here.

### 2. Blocker: an edit saved after an archive reverts the archive

- **Where:** [entry.py:1113-1119](../../src/iqdm/entry.py#L1113-L1119)
  (`build_recording` in edit mode), [entry.py:1218-1234](../../src/iqdm/entry.py#L1218-L1234)
  (`save_edit`) and [repository.py:319-345](../../src/iqdm/db/repository.py#L319-L345)
  (`update_recording`).
- **What is wrong:** edit mode copies `storage_root`, `rel_path`, `archive_state` and
  `archived_at` from the recording as it was loaded. Without a rescan it also copies
  the channels' counts, sizes and times. `update_recording` writes all of them. No
  step checks that the stored row is still the one the edit loaded. SPEC section 8
  keeps the Log tab usable while an archive runs, and other PCs share the database.
- **Failure:** a user opens Edit entry on a local recording. The recording is then
  archived, checked and its laptop copy deleted, on this PC or another one. The user
  corrects a remark and saves. The recording is `local` again, `archived_at` is empty,
  and it points at the laptop folder, which no longer exists. The NAS copy and the
  transfer history remain, but nothing in the app leads back to them. Delete laptop
  copy then refuses, because the recording no longer points at the archive, so no
  further data is lost. The same save also undoes the counts, sizes and times that a
  Check archive wrote for a legacy recording (D71) after the edit was opened.
- **Confirmed by:** `test_finding_2_an_edit_saved_after_an_archive_reverts_it`. The
  test saved what edit mode saves, a copy of the loaded recording with new remarks.
  After the save the recording was `local`, `archived_at` was None, and it pointed at
  the deleted laptop folder. The D71 case was confirmed by reading the code only.

### 3. Should fix: "Partly deleted" stays after a complete delete

- **Where:** [movecopy.py:360-385](../../src/iqdm/movecopy.py#L360-L385) (`laptop_copy`)
  and [operations.py:691-701](../../src/iqdm/transfer/operations.py#L691-L701).
- **What is wrong:** the laptop copy counts as deleted when the delete rows'
  `n_files` reach the archive's file count. A delete row counts only the files it
  deleted. Files that were already gone (`already_gone`) are not counted.
- **Failure:** one laptop file of 12 was moved away by hand before Delete laptop copy.
  The delete finished as passed, with 11 deleted and 1 already gone. The tab shows
  "Partly deleted: 1 file remain in … Delete the rest." A second delete run deletes
  nothing and passes, and the same text stays. The text also has a grammar slip,
  "1 file remain".
- **Confirmed by:**
  `test_finding_3_a_delete_of_a_copy_with_a_file_already_gone_stays_partly_deleted`.

### 4. Minor: the delete module's docstring disagrees with its code

- **Where:** [delete.py:9-10](../../src/iqdm/transfer/delete.py#L9-L10).
- **What is wrong:** the docstring says the check before delete must have "started
  after the archive finished". Since D74, `checked_before_delete()` compares the row
  ids ([delete.py:79-95](../../src/iqdm/transfer/delete.py#L79-L95)), and the function's
  own docstring says so.
- **Failure:** a maintainer who reads the module text expects a time comparison,
  which D74 removed.
- **Confirmed by:** reading the code.

### 5. Minor: D55 does not say that D74 amended it

- **Where:** [DECISIONS.md](../DECISIONS.md), the index row of D55 ("Active") and its
  text, "`delete.py` refuses to delete unless such a check passed after the archive
  finished".
- **What is wrong:** D74 replaced the time comparison with the order of the rows. The
  index rows of D5 and D19 show how an amended decision is marked. SPEC section 8
  states the current rule correctly.
- **Confirmed by:** reading DECISIONS.md and SPEC.md.

### 6. Minor: "NAS roots" in two visible texts

- **Where:** [app.py:33-36](../../src/iqdm/app.py#L33-L36) (`CLEAR_LOG_TAB_QUESTION`, a
  dialog) and [entry.py:1001](../../src/iqdm/entry.py#L1001) (a Log tab checklist line).
- **What is wrong:** D38 renamed "NAS roots" to "NAS locations" on screen. The Settings
  tab and the user guide use "NAS locations".
- **Failure:** a user reads "outside the configured NAS roots" and finds no such
  setting.
- **Confirmed by:** reading the code. `tests/test_user_text.py` checks for key names,
  decision numbers and database internals, so it does not catch an old term.

### 7. Minor: "1 files" in the delete dialog and its result

- **Where:** [transfer_tab.py:1214](../../src/iqdm/gui/transfer_tab.py#L1214) and
  [transfer_tab.py:1250-1256](../../src/iqdm/gui/transfer_tab.py#L1250-L1256).
- **What is wrong:** the texts use `f"{n:,} files"` where the rest of the tab uses
  `files_text()`.
- **Failure:** a recording with one file left gives "1 files … will be deleted" and
  "Deleted 1 files from the laptop."
- **Confirmed by:** reading the code.

### 8. Minor: "manifest" in a refusal shown to the user

- **Where:** [operations.py:493-496](../../src/iqdm/transfer/operations.py#L493-L496)
  with the messages of [manifest.py](../../src/iqdm/transfer/manifest.py).
- **What is wrong:** the app calls the manifest a "file list" on screen. A manifest
  that cannot be read gives "The file list cannot be used: the manifest C:\…\transfer-7-….json
  changed after it was written".
- **Confirmed by:** reading the code; `test_delete_refuses_a_changed_manifest` in
  [test_operations.py](../../tests/test_operations.py) matches that text.

### 9. Minor: the Log tab's format labels differ from the user guide

- **Where:** the Log tab, section "3 · File format", and
  [USER_GUIDE.md](../USER_GUIDE.md) section 3.
- **What is wrong:** the guide names "byte order" and "header size". The tab shows
  "Endianness" and "Header bytes", and the dropdowns show the stored values
  `interleaved_iq` and `little`, where the guide writes "interleaved I then Q" and
  "little-endian".
- **Confirmed by:** the screenshots `dev/review/shots/1-log-light.png` and
  `1-log-dark.png`.

### 10. Minor: a leftover package for transfer scripts

- **Where:** `src/iqdm/transfer/scripts/__init__.py` ("Transfer script generators
  behind the ScriptGenerator interface.") and the docstring of
  `src/iqdm/transfer/__init__.py`, which names "scripts".
- **What is wrong:** D48 removed the scripts, and SPEC section 9 no longer lists the
  folder. The package is empty apart from that docstring. No module imports it, and
  the build's analysis files in `build/work-review-1` do not name it.
- **Confirmed by:** `ls`, reading both files, and a search of the build's work folder.

### 11. Minor: `upgrade()` on a file made before D73 raises `IndexError`

- **Where:** [migrations.py:148-154](../../src/iqdm/db/migrations.py#L148-L154).
- **What is wrong:** D73 makes a version 1 file without `projects` count as
  `NEEDS_UPGRADE`. `upgrade()` then plans the steps from version 1 to version 1, gets
  an empty list and reads `steps[0]`.
- **Failure:** an `IndexError` in place of a `MigrationError` that names the cause.
  No backup is written and the file is unchanged. The GUI has no upgrade action yet
  (O19), so only code reaches this.
- **Confirmed by:** `test_upgrade_of_a_version_1_file_without_projects`.

### 12. Minor: SPEC section 9 leaves out `transfer/uncached.py`

- **Where:** [SPEC.md](../SPEC.md) section 9, the layout.
- **What is wrong:** [uncached.py](../../src/iqdm/transfer/uncached.py) reads files
  past the PC's cache for the check before delete (D55). The layout lists every other
  module of `transfer/`.
- **Confirmed by:** reading SPEC.md and `ls src/iqdm/transfer`.

### 13. Minor: out-of-date lines in STATUS.md

- **Where:** [STATUS.md](../STATUS.md), "Files for the user to remove".
- **What is wrong:** "`dev/test.db` … Move it out of the repository before the NAS
  test" refers to a test that ran on 2026-10-05 and 2026-10-09. `dev/test.db` is
  listed twice. The list does not yet name `dist/m7-4`, `build/work-m7-4` and
  `build/m7-4-build.log`, which `dist/m8-1` superseded.
- **Confirmed by:** reading STATUS.md and `ls build`.

### 14. Minor: the D73 check compares tables and columns only

- **Where:** [version.py:56-87](../../src/iqdm/db/version.py#L56-L87).
- **What is wrong:** a file that has every table and column of `schema.sql` counts as
  current, even when a CHECK constraint or a trigger differs. A database made before
  D64 has the old `operation` CHECK and triggers. It also lacks `projects`, so D73
  catches it today. A later in-place edit of a constraint alone would not be caught.
  After O20 freezes the schema, every change is a numbered migration, so this limit
  matters only until then.
- **Confirmed by:** reading the code.

### 15. Minor: the user guide does not say how to fix a wrong archive state

- **Where:** [USER_GUIDE.md](../USER_GUIDE.md) section 6 and D41.
- **What is wrong:** D41 leaves removing or correcting an entry as "a manual database
  job". No document says how to do that job safely on the shared catalogue, for
  example after finding 2.
- **Confirmed by:** reading the documents.

### 16. Minor: README's run examples use `dev/m3.db`

- **Where:** [README.md](../../README.md), "Run".
- **What is wrong:** STATUS says that `dev/m3.db` was made before D64 and refuses
  archive rows. It was also made before D73, so the app now refuses to open it. On a
  fresh checkout the file does not exist. `db_check.py create dev/m3.db` refuses an
  existing file, so on this PC the README's own command cannot make a new one.
- **Confirmed by:** reading README.md and STATUS.md; `ls dev` shows `m3.db`.

## Checked and found consistent

- **Deletion.** [delete.py](../../src/iqdm/transfer/delete.py) holds the only
  `.unlink()` and `.rmdir()` in `src/` (Grep tool over `src/iqdm`).
  [test_architecture.py](../../tests/test_architecture.py) and ruff TID251 enforce that.
  The conditions match SPEC section 8, D52, D55 and D74: a passed archive with a
  manifest, the manifest's SHA-256, a passed check before delete written after the
  archive (row id), the recording pointing at the archive's destination, and before
  each file the NAS copy and the laptop file at the manifest size. Relative paths go
  through `safe_rel_path()`, links are refused, and only empty folders are removed.
  Finding 1 is the gap in that chain.
- **Files created or overwritten.** The writes in `src/` match the tables in
  [M6.md](M6.md) ("Code paths that delete or overwrite a file") and [M7.md](M7.md)
  ("Code that creates or overwrites a file"). The copy engine renames a `.partial`
  file only when no file has the target name, and Windows refuses an existing target
  as well. Manifests, the migration backup and the legacy report use exclusive
  create. `create_database()` refuses an existing path. `config.save_config()`
  replaces `config.toml.new`, `config.toml.bak` and `config.toml` by design (D31,
  D35).
- **Connections.** [connection.py](../../src/iqdm/db/connection.py) sets
  `foreign_keys`, `busy_timeout = 5000` and the rollback journal; it switches a WAL
  file back to `DELETE` on a write connection. Writes use `BEGIN IMMEDIATE` with
  pauses of 1 s and 2 s (D7). Every caller opens and closes per operation. Reads in
  the Viewer use `mode=ro`.
- **D73 on every connection.** `connect()` calls `schema_status()`, which builds
  `schema.sql` in memory once (`@cache`) and reads the file's columns with one query.
- **Transfers.** Selection rescans the folder (D53) and applies `start <= t < end`
  (D49). Resume skips files of the right size, and verification hashes them unless
  the mode is `none` (D51, D63). Stop finishes the row as `skipped` with
  "Stopped after N of M files". Check archive takes counts and times from the folder
  only for channels without counts and logs that check as `skipped` (D71).
- **GUI threads.** Scans, previews, transfers, checks, deletes, database reads and
  writes, New database and the database check all run through the `TaskRunner`.
- **D70.** The tab title, the three-button question and the close question follow
  SPEC section 4 ([app.py](../../src/iqdm/app.py) `ask_unsaved_settings`,
  `closeEvent`).
- **D73 on screen.** The screenshots show "Project (optional)" with "No project" and
  "Add project" in the Log tab, and the Project column and filter in the Viewer.
- **Packaging.** [iqdm.spec](../../build/iqdm.spec) bundles `schema.sql` for both
  programs, excludes PySide6 from the console program, and writes the three files with
  `open("xb")`. The defaults file is read only from the program folder of a packaged
  build (`defaults_path_for()` in [app.py](../../src/iqdm/app.py)).
- **The user guide's labels.** Every button and section name in
  [USER_GUIDE.md](../USER_GUIDE.md) exists in the source, apart from finding 9.
- **M8.md.** Its commit range `7bb2cca` to `9751b22` holds 7 commits, and its test
  counts match this run.

## Unconfirmed suspicions

- **Path work on the Qt main thread.** The Log tab splits the folder path on every
  change of the folder field ([log_tab.py:510-526](../../src/iqdm/gui/log_tab.py#L510-L526)).
  For a drive letter that calls `WNetGetConnectionW`. The Settings tab's New database
  checks `target.exists()` on the main thread
  ([settings_tab.py:774](../../src/iqdm/gui/settings_tab.py#L774)). Neither was timed
  against a disconnected mapped drive or a slow share.
- **A network error during a check.** An `OSError` from `stat()` inside
  `verify_copy()` is not caught, so Check before delete or Compare with laptop copy
  would leave its `check` row without `finished_at`. Check rows are not in the
  unfinished list, so the row would stay "not finished" in the history.
- **The legacy import and other SQLite errors.** `legacy.main()` catches `OSError`,
  `DatabaseError` and `ValueError`. A `sqlite3.IntegrityError` other than a repeated
  location would end the command with a traceback. No input that causes one was found.
- **A read-only connection and a hot journal.** If a PC stops during a write, the next
  read-only connection (`mode=ro`) cannot roll back the journal. Whether SQLite then
  refuses the read on SMB was not tested.

## Could not be checked here

- Anything on the NAS: SMB locking, reads past the cache, throughput, and long paths
  on a share. A fix for finding 1 that compares file identity needs a check on the NAS,
  because SMB servers report file IDs in different ways.
- Real recordings, the real legacy database and the real catalogue.
- The GUI by eye on Windows in dark mode. The screenshots are offscreen renders.
- Two PCs at once, including finding 2 across PCs. The test ran on one database file.

## Points a new maintainer would miss

- The safety of the delete chain rests on the archive destination being a different
  folder from the laptop folder. At `e6f0569` only path text proves that (finding 1).
- Edit mode writes every column of a recording, including its location and archive
  state (finding 2).
- No document describes the release steps: version bump, build from `main`, release
  notes and the O20 snapshot. D72 lists them; README has no section for them.
- The `dev/review/` scripts exist only on this PC.

## Build output and files for the user to remove

- `dist/review-1/`, `build/work-review-1/` and `build/review-1-build.log`.
- `dev/review/` (the reproductions, the screenshot script, `shots/` with a scratch
  database and a synthetic recording).
- The pytest folders under `%TEMP%\pytest-of-Perry\` hold a directory junction from
  the reproduction of finding 1. Remove it as a link, so that its target is not
  touched. Its target held no files after the test.

## Recommendation and question

Do not release 1.0 at `e6f0569`. Fix findings 1 and 2 first; fix finding 3 and the
minor findings in the same pass if the user agrees. Then build again and repeat the
checks above. A fix plan follows in chat, for approval: which findings to fix, how,
and the tests for each.
