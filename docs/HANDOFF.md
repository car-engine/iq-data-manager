# Handoff: IQ Data Manager after release 1.3.0

Read this file first when you pick up the repository. It says where the project
stands, how work proceeds, and what is still open. It points to the other documents
for the detail. Last updated: 2026-10-27, at the release of version 1.3.0.
[STATUS.md](STATUS.md) is updated after every piece of work and is the current record.

## 1. State

| | |
| --- | --- |
| Version | 1.3.0, tag `v1.3.0` on `7eb9ab6` (annotated, pushed, 2026-10-27). Earlier: 1.2.1 (`v1.2.1` on `485434f`), 1.2.0 (`v1.2.0` on `616b18c`), 1.1.1 (`v1.1.1` on `3108c63`), 1.1.0 (`v1.1.0` on `ed1afe8`), 1.0.0 (`v1.0.0` on `674434c`). |
| `main` | `7eb9ab6` at the release, pushed to `origin`; a later commit records the release |
| Tests | 2,014 passed, 4 skipped (`pytest`); `ruff check` clean |
| Release build | `dist/release-1.3.0/IQDataManager/` on the development PC, built from `7eb9ab6`. The older `dist/release-*` folders stay until the team runs 1.3.0. `dist/` is gitignored, so a new PC builds its own with README "Build". |
| Schema | Version 1, unchanged since 1.0.0 (section 5) |
| Milestones | 0 to 8 done, then work after 1.0 from open items (STATUS.md, "Work after 1.0"). |
| In use | Yes. The real catalogue exists, the pilot passed (2026-10-20), the team no longer uses the legacy logging scripts, a backup of the catalogue runs outside the app (O22), and the field checks of 1.1 passed (2026-10-22). The user's manual tests of 1.2 and 1.2.1 passed (2026-10-23), and those of 1.3.0 (2026-10-24 and 2026-10-27). |
| Next | No ready items. The team's feedback on 1.3.0, with the prompt "Work after a release" in [KICKOFF.md](KICKOFF.md). The field checks of 1.3.0 are in section 6. |

The app is a Windows desktop tool (Python 3.12, PySide6) that logs RF IQ recordings
into a shared SQLite catalogue on the NAS, and copies, archives and deletes recordings
with verification. The team uses the packaged build; the laptops have no Python.

## 2. Read order

1. `CLAUDE.md`: the safety rules and the conventions. They override everything else.
2. This file.
3. [STATUS.md](STATUS.md): open items, pending checks, files for the user to remove,
   and "Notes for agents", which records how the safety hook and the tools behave in
   this repository. Read the notes before the first shell command.
4. [SPEC.md](SPEC.md): the current requirements. Read the sections your change
   touches.
5. [DECISIONS.md](DECISIONS.md): the reasons, D1 to D102. Every SPEC rule names its
   decision.
6. The latest reports, of version 1.3.0, which describe the Archive / copy tab as it
   stands:
   [reports/2026-10-23-transfer-pages.md](reports/2026-10-23-transfer-pages.md),
   [reports/2026-10-23-check-after-archive.md](reports/2026-10-23-check-after-archive.md),
   [reports/2026-10-23-queue-asks-for-folder.md](reports/2026-10-23-queue-asks-for-folder.md)
   (with the table "Code paths that delete or overwrite a file" for the version),
   [reports/2026-10-24-queue-actions.md](reports/2026-10-24-queue-actions.md),
   [reports/2026-10-24-transfer-field-marks.md](reports/2026-10-24-transfer-field-marks.md)
   and [reports/2026-10-24-quoted-names.md](reports/2026-10-24-quoted-names.md). Of
   version 1.2.1:
   [reports/2026-10-23-wheel-guard.md](reports/2026-10-23-wheel-guard.md) (with
   "Notes for version 1.3.0", the plan that 1.3.0 started from),
   [reports/2026-10-23-batch-log-rf-rows.md](reports/2026-10-23-batch-log-rf-rows.md),
   [reports/2026-10-23-logged-by-typed.md](reports/2026-10-23-logged-by-typed.md) and
   [reports/2026-10-23-required-field-marks.md](reports/2026-10-23-required-field-marks.md),
   which holds the manual test. Of version 1.2:
   [reports/2026-10-23-band-from-fc.md](reports/2026-10-23-band-from-fc.md),
   [reports/2026-10-23-delete-entry.md](reports/2026-10-23-delete-entry.md),
   [reports/2026-10-23-log-several-folders.md](reports/2026-10-23-log-several-folders.md)
   and [reports/2026-10-23-queue-entry-check.md](reports/2026-10-23-queue-entry-check.md).
   They describe the Log tab as it stands, and what was tested. For 1.1:
   [reports/2026-10-22-review-1.1.0.md](reports/2026-10-22-review-1.1.0.md) and the two
   1.1.1 reports it links to. For the history before 1.1:
   [reports/M8.md](reports/M8.md) and
   [reports/2026-10-11-release-review.md](reports/2026-10-11-release-review.md).
7. For a user-facing change: [USER_GUIDE.md](USER_GUIDE.md) and
   [RELEASE_NOTES.md](RELEASE_NOTES.md), which ship in the program folder.

## 3. How work proceeds

Milestones no longer apply. The user starts each session with a prompt from
[KICKOFF.md](KICKOFF.md): a ready prompt for the next version, or the templates "Work
after a release" and "Review of a release". Earlier prompts are in
[KICKOFF_ARCHIVE.md](KICKOFF_ARCHIVE.md). Each piece of work follows the same cycle as
a milestone did:

1. **Record it.** A request or a fault gets an open item in STATUS.md, "Open items",
   with the next free number (STATUS.md names it; O65 is next on 2026-10-27), a
   proposed default and its origin.
2. **Plan.** Propose a plan with its test list in chat, and wait for approval
   (CLAUDE.md, "Workflow"). The safety hook blocks plan files outside the
   repository, so plans stay in chat.
3. **Branch.** One branch per piece of work, named after it, for example
   `viewer-multi-filter`. Never commit straight to `main`.
4. **Implement with tests.** Run `pytest` and `ruff check` before declaring it done.
5. **Record the decision.** A new entry in DECISIONS.md (D103 is next on 2026-10-27),
   the current requirement in SPEC.md, and the item moved to "Closed items" in
   STATUS.md.
6. **Report.** `docs/reports/<YYYY-MM-DD>-<topic>.md`, following
   [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md). Update STATUS.md in the same commit.
7. **Manual test.** Before a release, the agent gives the user a checklist as an HTML
   page under `dev/`, with small synthetic data (STATUS.md, "Notes for agents"). The
   user runs it on the development PC.
8. **Merge and release** only with the user's approval (section 4). After the merge,
   delete the branch with `git branch -d`, which refuses a branch that is not fully
   merged, and on GitHub if it was pushed. Both need the user's approval.
9. **Next prompt.** At the end of a version, draft the next ready prompt in
   KICKOFF.md for the user, and move the used one to KICKOFF_ARCHIVE.md.

A change that copies, renames or deletes files updates the table "Code paths that
delete or overwrite a file" (last full list in [reports/M6.md](reports/M6.md), with
changes in [reports/M7.md](reports/M7.md), [reports/M8.md](reports/M8.md) part 2,
the reports of 1.1 and 1.1.1, and for 1.3.0
[reports/2026-10-23-queue-asks-for-folder.md](reports/2026-10-23-queue-asks-for-folder.md))
in its report. A change that deletes catalogue rows
lists them the same way.

## 4. Versions and releases

- **Numbers.** `1.x.y` for fixes that change no feature and no database format, such
  as 1.1.1; `1.x.0` for new features, such as 1.2.0; any change to `schema.sql` after
  the real catalogue exists needs a migration (section 5) and at least a new minor
  version.
- **The version** lives only in `src/iqdm/__init__.py` (`__version__`).
  `pyproject.toml` reads it. The window title and both programs' `--version` show it.
- **Release steps,** each with the user's approval where marked:
  1. Merge the work into `main` as a fast-forward (approval).
  2. On a branch: set `__version__`, add a section at the top of
     [RELEASE_NOTES.md](RELEASE_NOTES.md) in plain words for the team, update
     USER_GUIDE.md if the screen changed; run `pytest` and `ruff check`; merge.
  3. Build from `main` into new folders with README "Build", for example
     `dist/release-<version>`. Run `--smoke-test`, `IQDataManager-check.exe --help`
     and `--version`, and the `longPathAware` check. Compare the shipped files
     (`USER_GUIDE.md`, `RELEASE_NOTES.md`, `defaults.example.toml`) with their
     sources.
  4. Tag the commit the build came from: `git tag -a v<version>` (approval).
  5. Push `main` and the tag (approval).
  6. Record the release in STATUS.md and this file, and push that commit.
- The build folder's files are written by `build/iqdm.spec` after `COLLECT`. Add or
  remove a shipped file there and in README "Build" and USER_GUIDE.md section 1.

## 5. The database format after 1.0

- **Version 1 is frozen** (O20, D77, 2026-10-20). The real catalogue was made with
  the 1.0.0 build. `tests/schemas/v1.sql` holds `schema.sql` of `v1.0.0`.
  `tests/test_schema_freeze.py` checks that a database built from it and upgraded has
  the structure of the current `schema.sql`. While `LATEST_VERSION` is 1, it also
  fails any change to a statement of `schema.sql`. Do not edit `schema.sql` in place.
- **The first real schema change** brings three things together: a numbered
  migration in `src/iqdm/db/migrations.py` with `LATEST_VERSION` raised (D6), the
  "Upgrade database" action in the Settings tab (O19), and a backup before the upgrade
  (`migrations.backup_database()`, already written and tested). The app never migrates
  on its own (D6). Every PC must then run the new version, because an older version
  refuses a newer database.
- The D73 check in `db/version.py` treats a file at the current version that lacks a
  table or column of `schema.sql` as older. It compares tables and columns only, not
  constraints or triggers (release review, finding 14). With numbered migrations this
  limit no longer matters.
- Versions 1.1.0 to 1.3.0 changed no schema statement.

## 6. Outstanding items

STATUS.md, "Open items", is the current list. At this handoff:

### Done in version 1.3.0

From the team's feedback on 1.2: O58 (the Archive / copy tab in three pages, D96),
O57 (Check before delete straight after each archive, D97) and O59 (queue items wait
for their folder, D98). From the user's first manual test of 1.3.0: O63 (the page after
Add to queue, D99), O64 ("Forget", D100), O60 and O61 (frames on the Archive and Copy
pages, and the Check page's line, D101) and O62 (names of controls in quotation marks,
D102). The six reports are listed in section 2.

### Done in version 1.2.1

O56 (the mouse wheel never changes a field, D92), O55 (the log rows in "Several
folders", D93), O53 (Logged by typed by the user, D94) and O54 (fields to fill in or
correct are framed, D95), from the team's feedback on 1.2. The reports are the four
`docs/reports/2026-10-23-*.md` of version 1.2.1 in section 2.

### Done in version 1.2.0

O50 (the band from fc, D88), O39 (deleting an entry added by mistake, D89), O51
(several folders with one set-up, D90) and O52 (a deleted entry's number given
again, D91). The reports are in `docs/reports/2026-10-23-*.md`; STATUS.md, "Work
after 1.0", lists them. `AUTOINCREMENT` for `recordings.id` (O52) waits for the first
schema change; D91 holds the reason.

### Open items

| ID | Item | When |
| --- | --- | --- |
| O19 | "Upgrade database" in the Settings tab | With the first schema migration |
| O37 | Small files copy slowly to the NAS | Measure first; not needed for 1.x. The team has not found it a problem (2026-10-22). |
| O40 | Unconfirmed suspicions from the release review: path work on the Qt main thread, a network error during a check, SQLite errors in the legacy import, a read-only connection after a crash | When a fault points at one of them. None seen in use (2026-10-22). |

### Not tested, or tested only partly

| What | Why | Who and when |
| --- | --- | --- |
| The cost on the NAS of the D73 check per connection and of the D75 identity check per file | Not measured. Locally neither is measurable. | When O37 is measured |
| Check before delete through a Windows share of the same PC | Fails with WinError 87 for files whose size is not a multiple of 512 bytes, most likely (D85). The real NAS passed. | Known limit; manual tests use file sizes that are multiples of 512 |
| The GUI by eye in dark mode on Windows | Offscreen renders and the user's checks only | User, with each build |
| Version 1.2 on the NAS: several real folders of a day (scan time, Cancel during a long scan), and a delete while a second PC works on the catalogue | The manual test used local synthetic data on one PC | User, in the field |
| Version 1.2.1: the mouse wheel on a laptop's touchpad, and a theme switch while the app runs on a team PC | Step 1.7 of the manual test was optional and not run; tests cannot send real wheel input | User, in the field |
| Version 1.3.0: Check before delete after each archive on the real NAS, for a queue of real recordings overnight | The manual tests used a Windows share of the development PC and synthetic data | User, in the field |
| Version 1.3.0: Compare with laptop copy on the Check page, and the Archive page's start at the sampled hashes when Settings says "Sizes only" | Automated tests only; the test data held no recording logged on the NAS | User, when it comes up |

The checks of 1.1 on the NAS and in the field passed (STATUS.md, "Pending checks for
the user"). The user's rollout steps after 1.0 are done: the real catalogue, the
backup (O22), the pilot and the cut-over from the legacy scripts.

### Out of scope for version 1

SPEC section 13: a Linux build, transfer scripts (D48), gap storage in the database,
user accounts, RF chain templates, and deleting an entry with an archive, a copy or
a delete in its history (D89). The business logic imports no Qt. Its Windows-specific
parts are few: `location.mapped_drive_unc()`, `transfer/uncached.py`,
`transfer/power.py`, `pathcheck.long_paths_enabled()` and the `%APPDATA%` settings
path in `config.py`. The first four check the platform and fall back elsewhere. The
settings path needs `APPDATA`, so a Linux build would need another settings location.

## 7. Code map

| Area | Where | Notes |
| --- | --- | --- |
| Entry points | `app.py` (window, `--config`, `--db`, `--smoke-test`), `check_main.py` (console program) | |
| Database | `db/schema.sql`, `db/connection.py`, `db/version.py`, `db/repository.py`, `db/migrations.py`, `db/legacy.py` | All SQL lives in `db/`; only `db/` imports `sqlite3` |
| Logic without Qt | `entry.py` (Log tab; deleting an entry, D89), `bands.py` (the band list, D88), `batchlog.py` (several folders, D90), `deletion_record.py` (the copy of a deleted entry, D89), `templates.py` (Log tab templates, D80), `transferqueue.py` (Archive / copy queue, D81, D86; items that wait for a folder and the page after an add, D98, D99), `recorderlog.py` (values from the recorder's log, D82; a template after the log, D87), `viewer.py` (Viewer), `movecopy.py` (Archive / copy tab: the pages and `page_for()`, D96; `check_after_archive()`, D97; `form_marks()`, D101), `legacy.py`, `config.py`, `location.py`, `models.py` | Tested without a display |
| Transfers | `transfer/selection.py`, `pathcheck.py`, `copier.py`, `verify.py`, `uncached.py`, `manifest.py`, `delete.py`, `operations.py` | `delete.py` is the only module that deletes files (`tests/test_architecture.py`, ruff TID251) |
| GUI | `gui/viewer_tab.py`, `log_tab.py`, `transfer_tab.py`, `settings_tab.py`, `workers.py` (`TaskRunner`), `widgets/` | Work over about 100 ms runs in the `TaskRunner` |
| Diagnostics | `diagnostics/`, wrapped by `tools/` and `IQDataManager-check.exe` | `diagnostics/fixtures.py` makes synthetic recordings for tests and manual tests |
| Viewer filter | `models.RecordingFilter`, `viewer.parse_filter()`, `repository._filter_sql()`, `gui/widgets/check_combo.py` in `gui/viewer_tab.py` | Several sites, projects (with "No project") and bands since D78 |
| Log tab state | `gui/log_tab.py`: `_carried` (kept band and fc, D79), `_log_values` and `_log_applied_for` (the recorder's log, D82, D87), `_ChannelRow.fc_log`, `fs_log` and `band_auto` (the italic marks), `_ChannelRow.fc_before` (the fc the band last followed, D88) | Code that sets a field without `textEdited` must set or clear these flags itself |
| Several folders | `gui/log_tab.py`: `_folders`, `_selected_key`, `_views`, `_checks` (D90); `gui/widgets/folder_table.py` | Section 4 shows the selected folder's channels; `_sync_selected()` keeps what was typed there with that folder. A scanned channel keeps its size counts (`ChannelScan.size_counts`), so a refresh of 50 folders stays near 50 ms. The selected folder's log rows show under section 5 (`_show_log_rows()`, `batchlog.log_shown()`, D93) |
| Field frames | `entry.field_marks()` (D95), `gui/log_tab.py`: `_show_field_marks()`, `_show_mark()`, `_restyle_sheets()`; `gui/widgets/mark_frame.py` for dropdowns | The checklist's field lines are built from `field_marks()`. A dropdown gets no style sheet; its `MarkFrame` paints the frame. A widget with a style sheet keeps its old palette after a theme switch until the sheet is set again |
| Mouse wheel | `gui/widgets/wheel_guard.py`, installed by `MainWindow` (D92) | An application event filter; tests cannot send the real wheel input that Qt passes to the parent |
| Archive / copy pages | `gui/transfer_tab.py`: `pages`, `page()`, `show_page()`; `dest_edit` and `hash_combo` are properties that return the field of the page shown (D96). `_show_field_marks()` frames the folder, destination, time and channel fields (D98, D101) | The pages lock while an operation started from a page runs, not during a queue run (D98). Check before delete reads the Archive page's Compare, Compare with laptop copy the Check page's, whatever page is shown |
| Quoted names | `tests/user_text_names.py`, `tests/test_user_text.py` (`unquoted_names()`) (D102) | A control name in a sentence needs double quotes, or the text test fails. Add the name of a new control to `user_text_names.py` |

## 8. Traps that cost time before

The full list is "Notes for agents" in STATUS.md. The ones met most often:

- **The safety hook reads the whole shell command.** Words such as `rm`, `rmdir`,
  `rmtree`, `robocopy`, `.unlink(` and `os.remove`, and any UNC path, block it, even
  inside a commit message, a heredoc or a search pattern. Search for such words with
  the Grep tool. Write and change files only with the Write and Edit tools.
- **The hook blocks plan files** under `~/.claude/plans/`. In plan mode, write the
  plan in chat, then call ExitPlanMode.
- **No agent deletes files.** Add each file to remove to STATUS.md, "Files for the
  user to remove".
- **No agent touches a network path.** Checks on the NAS are the user's. A share of
  the development PC can stand in for the NAS in a manual test; Check before delete
  through it needs file sizes that are multiples of 512 bytes (section 6).
- **Builds go into new folders.** Never pass `--noconfirm` or `--clean`.
- **Git:** stage files by path; only `status`, `diff`, `log`, `add` and `commit`
  without approval. Merging, tagging and pushing need the user's approval.
- **`ruff format` only on the files you change.** `ruff check` is the gate.
- **A replace across a file can hit strings.** In Milestone 8, renaming a module
  alias in a test also changed a `monkeypatch` target string.
- **Tests that need two names for one folder** use `junction()` in
  `tests/conftest.py`. Directory junctions need no privilege; symbolic links do, and
  three tests skip for that reason.
- **`entry.save_edit()` needs `original=`,** the recording as the edit loaded it
  (D76).
- **User-facing text** follows CLAUDE.md, "User-facing text";
  `tests/test_user_text.py` checks each tab and the dialog texts. Add new texts there.
  Since D102 it also fails a control name used in a sentence without quotes.
- **A test that fails while the queue holds an item hangs the suite:** the window's
  teardown asks a real question. Run long suites with `timeout` in front (STATUS.md,
  "Notes for agents"); in 1.3.0 a changed text did this once.
- **A throwaway test under `dev/`** can reuse the suite's fixtures: insert `tests/` in
  `sys.path` and import the fixtures by name, as the review probes of 1.1.0 did
  (review report, "Points a new maintainer would miss").
