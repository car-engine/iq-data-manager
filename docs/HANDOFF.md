# Handoff: IQ Data Manager after release 1.1.1

Read this file first when you pick up the repository. It says where the project
stands, how work proceeds, and what is still open. It points to the other documents
for the detail. Last updated: 2026-10-22, at the handoff for version 1.2.
[STATUS.md](STATUS.md) is updated after every piece of work and is the current record.

## 1. State

| | |
| --- | --- |
| Version | 1.1.1, tag `v1.1.1` on `3108c63` (annotated, pushed, 2026-10-22). Earlier: 1.1.0 (`v1.1.0` on `ed1afe8`), 1.0.0 (`v1.0.0` on `674434c`). |
| `main` | `3108c63` at the release, pushed to `origin`; later commits record the release and this handoff |
| Tests | 1,781 passed, 4 skipped (`pytest`); `ruff check` clean |
| Release build | `dist/release-1.1.1/IQDataManager/` on the development PC, built from `3108c63`. `dist/release-1.1.0/` and `dist/release-1.0.0/` stay. `dist/` is gitignored, so a new PC builds its own with README "Build". |
| Milestones | 0 to 8 done, then work after 1.0 from open items (STATUS.md, "Work after 1.0"). |
| In use | Yes. The real catalogue exists, the pilot passed (2026-10-20), the team no longer uses the legacy logging scripts, a backup of the catalogue runs outside the app (O22), and the field checks of 1.1 passed (2026-10-22). |
| Next | Version 1.2: O50, O39, then O51 (section 6). The prompt is "Version 1.2" in [KICKOFF.md](KICKOFF.md). |

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
5. [DECISIONS.md](DECISIONS.md): the reasons, D1 to D87. Every SPEC rule names its
   decision.
6. The latest reports:
   [reports/2026-10-22-review-1.1.0.md](reports/2026-10-22-review-1.1.0.md) (the review
   of 1.1.0, parts 1 and 2), with
   [reports/2026-10-22-queue-fixes-1.1.1.md](reports/2026-10-22-queue-fixes-1.1.1.md)
   and [reports/2026-10-22-log-fixes-1.1.1.md](reports/2026-10-22-log-fixes-1.1.1.md).
   They describe the Log tab and the queue as they stand, and what was tested. For
   the history before 1.1: [reports/M8.md](reports/M8.md) and
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
   with the next free number (STATUS.md names it; O52 is next on 2026-10-22), a
   proposed default and its origin.
2. **Plan.** Propose a plan with its test list in chat, and wait for approval
   (CLAUDE.md, "Workflow"). The safety hook blocks plan files outside the
   repository, so plans stay in chat.
3. **Branch.** One branch per piece of work, named after it, for example
   `viewer-multi-filter`. Never commit straight to `main`.
4. **Implement with tests.** Run `pytest` and `ruff check` before declaring it done.
5. **Record the decision.** A new entry in DECISIONS.md (D90 is next on 2026-10-23),
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
changes in [reports/M7.md](reports/M7.md), [reports/M8.md](reports/M8.md) part 2 and
the reports of 1.1 and 1.1.1) in its report. A change that deletes catalogue rows
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
- Versions 1.1.0 and 1.1.1 changed no schema statement.

## 6. Outstanding items

STATUS.md, "Open items", is the current list. At this handoff:

### Version 1.2 (the user's order, 2026-10-22)

| ID | Item | Notes |
| --- | --- | --- |
| O50 | The band filled in from fc | Small; first. Bands overlap (VHF and Marine VHF); settings are per PC (D68); a kept band goes stale when the log changes fc (D79, D82). |
| O39 | Deleting an entry added by mistake | Small; second. Reverses D41 and SPEC section 13. `repository.delete_recording()` refuses every entry with transfer history, which includes all entries logged in place on the NAS (D2) and all legacy imports (D66). |
| O51 | Logging several recordings with one set-up | Last, after a full plan discussed with the user. The user's questions are in the prompt "Version 1.2" in KICKOFF.md. |

The prompt "Version 1.2" holds the user's own words for each item and what is known
so far.

### Other open items

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

The checks of 1.1 on the NAS and in the field passed (STATUS.md, "Pending checks for
the user"). The user's rollout steps after 1.0 are done: the real catalogue, the
backup (O22), the pilot and the cut-over from the legacy scripts.

### Out of scope for version 1

SPEC section 13: a Linux build, transfer scripts (D48), gap storage in the database,
user accounts, RF chain templates, and deleting catalogue entries in the GUI (D41,
which O39 revisits for 1.2). The business logic imports no Qt. Its Windows-specific
parts are few: `location.mapped_drive_unc()`, `transfer/uncached.py`,
`transfer/power.py`, `pathcheck.long_paths_enabled()` and the `%APPDATA%` settings
path in `config.py`. The first four check the platform and fall back elsewhere. The
settings path needs `APPDATA`, so a Linux build would need another settings location.

## 7. Code map

| Area | Where | Notes |
| --- | --- | --- |
| Entry points | `app.py` (window, `--config`, `--db`, `--smoke-test`), `check_main.py` (console program) | |
| Database | `db/schema.sql`, `db/connection.py`, `db/version.py`, `db/repository.py`, `db/migrations.py`, `db/legacy.py` | All SQL lives in `db/`; only `db/` imports `sqlite3` |
| Logic without Qt | `entry.py` (Log tab), `templates.py` (Log tab templates, D80), `transferqueue.py` (Archive / copy queue, D81, D86), `recorderlog.py` (values from the recorder's log, D82; a template after the log, D87), `viewer.py` (Viewer), `movecopy.py` (Archive / copy tab), `legacy.py`, `config.py`, `location.py`, `models.py` | Tested without a display |
| Transfers | `transfer/selection.py`, `pathcheck.py`, `copier.py`, `verify.py`, `uncached.py`, `manifest.py`, `delete.py`, `operations.py` | `delete.py` is the only module that deletes files (`tests/test_architecture.py`, ruff TID251) |
| GUI | `gui/viewer_tab.py`, `log_tab.py`, `transfer_tab.py`, `settings_tab.py`, `workers.py` (`TaskRunner`), `widgets/` | Work over about 100 ms runs in the `TaskRunner` |
| Diagnostics | `diagnostics/`, wrapped by `tools/` and `IQDataManager-check.exe` | `diagnostics/fixtures.py` makes synthetic recordings for tests and manual tests |
| Viewer filter | `models.RecordingFilter`, `viewer.parse_filter()`, `repository._filter_sql()`, `gui/widgets/check_combo.py` in `gui/viewer_tab.py` | Several sites, projects (with "No project") and bands since D78 |
| Log tab state | `gui/log_tab.py`: `_carried` (kept band and fc, D79), `_log_values` and `_log_applied_for` (the recorder's log, D82, D87), `_ChannelRow.fc_log` and `fs_log` (the italic mark) | Code that sets a field without `textEdited` must set or clear these flags itself |

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
- **A throwaway test under `dev/`** can reuse the suite's fixtures: insert `tests/` in
  `sys.path` and import the fixtures by name, as the review probes of 1.1.0 did
  (review report, "Points a new maintainer would miss").
