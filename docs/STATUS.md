# Project status

Read this file at the start of every session, after `CLAUDE.md`. Update it at the end
of every milestone and after any other significant work, in the same commit as the
report. Last updated: 2026-10-12 (Milestone 8: the release review and its fixes,
D75, D76).

## Current state

- **Milestone 8, Release 1.0 (D72), is in progress on branch `m8-release`**, from
  `main` at `1f8001b`. Not merged. Report: [reports/M8.md](reports/M8.md), parts 1
  and 2. At `4c81be5`: 1,607 tests pass and 4 skip; `ruff check` is clean. The build
  is `dist/m8-2`.
  - Part 1: D73 (a project for each recording) and D74 (transfer rows in the order
    they were written), approved on 2026-10-11.
  - Part 2: the release review
    ([reports/2026-10-11-release-review.md](reports/2026-10-11-release-review.md))
    found two blockers. Both are fixed: D75 compares file identity in the destination,
    verify and delete checks, so one folder under two names can no longer lose its
    only copy; D76 makes an edit save only over the entry it opened, so it can no
    longer undo an archive. The other approved findings are fixed too. Findings 14
    and 15 were left unchanged.
  - The user's checks of D73, D75 and D76 with `dist/m8-2` passed on 2026-10-12 on
    the development PC, with a Windows share standing in for the NAS (M8.md, part 2).
    Check before delete cannot read through a share of the same PC (WinError 87), so
    the delete step was not testable there. D75 is not yet tried on the NAS.
- **The second visit to the NAS (2026-10-09) passed,** with `dist/m7-4`. Locking
  between two PCs passed: PC B's write waited for the 30 s hold, retried once and
  passed after 11.8 s. This closes O21. Check before delete of every file of A
  (4,000,000,000 bytes) raised the received bytes of `netstat -e` by "3.x GB" by the
  user's memory; the exact numbers were not kept. Windows shows units of 2^30 bytes
  as "GB", in which A is 3.73 GB, so the reads went over the network: D55 is taken as
  confirmed. The legacy import and Check archive in a trial catalogue passed. The two
  PCs' clocks differed by about 50 s, which led to D74.
- For the Milestone 8 report: on 2026-10-11 the agent ran `sed -i.bak '' /dev/null`
  in the shell, against the notes for agents. It named no file of the repository and
  changed nothing (`git status` was clean).
- **Milestones 0 to 7 are merged into `main` and pushed.** Milestone 7 was merged as
  a fast-forward on 2026-10-06 and pushed the same day. Report:
  [reports/M7.md](reports/M7.md). 1,549 tests pass and 4 skip on `main`; three skips
  need the symbolic-link privilege, the other runs only off Windows. `ruff check` is
  clean.
- **D73 changes `schema.sql` in place.** Every database made before it (scratch
  databases on the NAS, the trial legacy catalogue, the `dev/` databases) lacks the
  project column; the app then reports it as an older version. Make such a database
  again.
- Milestone 7 added the packaged legacy import (D66, D71), "New database..." in the
  Settings tab (D67), the defaults file in the program folder (D68), the amber notes
  and the unsaved-settings question (D69, D70), long paths (D65, closes O33) and the
  user guide ([USER_GUIDE.md](USER_GUIDE.md)), all shipped in the build folder.
- **Still to do in Milestone 8:** the merge into `main`; version 1.0.0, the release build from `main` and
  release notes; the cut-over from the legacy logging scripts; the real catalogue
  with O20; the team's `defaults.toml`. Recommended: O22, and a pilot that also checks
  D75 on the NAS.
- **The NAS field test (D54) ran on 2026-10-05** with `dist/m7-2`, on a laptop with a
  10 GbE link. Every app step passed; results and throughput are in
  [reports/M6.md](reports/M6.md), "NAS field test results".
- The safety hook blocks an agent's shell command that holds a UNC path, so the user
  runs `migrate-legacy` and other checks with NAS paths by hand.
- D55–D62 closed O36, O11, O34, O35, O1, O10, O25 and O12. D63 hashes skipped files
  when a transfer resumes. D64 renamed the operation "move" to "archive" everywhere.
- Scratch databases made before D73, such as `dev/test.db` and `dev/m3.db`, count as
  an older version. Create a new one with `tools/db_check.py create` (or
  `IQDataManager-check.exe db-check create`).
- The diagnostics live in `src/iqdm/diagnostics/`; `tools/` holds wrappers, and the
  build holds the console program `IQDataManager-check.exe` (D57).
- All text on screen follows CLAUDE.md, section "User-facing text" (D38).
  `tests/test_user_text.py` checks the Viewer, Log, Settings and Archive / copy tabs.
- O21 is closed: the local part on 2026-10-02
  ([reports/2026-10-02-db-check.md](reports/2026-10-02-db-check.md)), the NAS part on
  the second visit (2026-10-09).

## Milestones

Scope of each milestone: `docs/SPEC.md` section 12.

| Milestone | Status | Branch | Commits | Report |
| --- | --- | --- | --- | --- |
| 0. Scaffold | Done | `main` | `dac3d8f`–`ccf08f3` | [M0](reports/M0.md) |
| 1. Database layer | Done, merged | `m1-database` | `d2e11b3`–`f832167`, `48d7749` (handoff documents), plus the commit that records the merge | [M1](reports/M1.md) |
| 2. Scanner | Done, merged | `m2-scanner` | `fa39b82`–`d764074`, plus the commit that records the merge | [M2](reports/M2.md) |
| 3. Log tab | Done, merged | `m3-log-tab` | `0569068`–`eed75f0`, `cbeab1e` (report), plus the commit that records the merge | [M3](reports/M3.md) |
| 3a. Settings tab (D29) | Done, merged | `m3a-settings` | `8298a97`–`f772059`, plus the commit that records the merge | [M3a](reports/M3a.md) |
| 4. Viewer tab | Done, merged | `m4-viewer` | `1f17daa`–`8b8bcce`, `fffe705` (report), `d1fb8c3` (D47), `dd8d95d` (D47 documents), plus the commit that records the merge | [M4](reports/M4.md) |
| 5. Transfer core | Done, merged | `m5-transfer-core` | `a2a7fb5`–`57b3899`, `e340c8c` (report), `9ce023e` (D54 test set), `ca5c145` (D54 documents), plus the commit that records the merge | [M5](reports/M5.md) |
| 6. Archive / copy tab | Done, merged; NAS field test run, two checks moved to Milestone 8 | `m6-move-copy-tab` | `7f1273b`–`95c9256`, `d6507a6` (report), `47a7f06` (manual-test fix), `ef6ef90` (report of the fix), plus the commit that records the merge | [M6](reports/M6.md) |
| 7. Packaging and migration | Done, merged | `m7-packaging-migration` | `e271362`–`cfa6d25`, plus the commit of the report | [M7](reports/M7.md) |
| 8. Release 1.0 (D72) | In progress | `m8-release` | `7bb2cca`–`9751b22` and `e6f0569` (part 1); `e016add` (review report)–`4c81be5` (fixes), plus the commit of part 2 | [M8](reports/M8.md) (parts 1 and 2), [release review](reports/2026-10-11-release-review.md) |

Commits between the milestones on `main`: `814417c` (decisions D1–D3 in the spec),
`89e94ac` (the user's PowerShell deny rule in `.claude/settings.json`), `6028895` and
`68fb49c` (D29, D30), `257244c` (documentation review), `77ed32c` (the user's
narrower UNC pattern in the safety hook), `a9079d5` (documents for the next agent
after Milestone 4) and the documentation review after Milestone 5 (branch
`docs-review-m5`).

## Open items

Questions and known gaps that are not yet decided. The default is what an agent
proposes unless the user decides otherwise. Raise each item in the plan for its
milestone. When it is decided, record it in `docs/DECISIONS.md`, update `SPEC.md`,
and move it to "Closed items" below. "M0 review <n>" refers to the table in
[reports/M0.md](reports/M0.md).

| ID | Item | Milestone | Proposed default | Origin |
| --- | --- | --- | --- | --- |
| O19 | GUI for the confirmed "Upgrade database" action | With the first real schema migration | A button in the Settings tab's database section, shown only when the schema needs an upgrade, plus a startup message that points to it. Deferred by D30; until then an older database gives a red status line (D38). | D6; D29; D30 |
| O20 | Frozen copy of the version 1 schema for testing future migrations | 8 | Snapshot `schema.sql` as `tests/schemas/v1.sql` when the first real database is created. | D4 |
| O22 | SQLite on SMB: scheduled backup of the catalogue outside the app | User; recommended in Milestone 8 (D72) | None yet; for example a NAS snapshot or a scheduled copy | M0 review 24 |
| O37 | Small files copy slowly to the NAS: about 18 to 25 ms per 64 KB file, with or without the flush, and more files at once help little. A day of 1 s files is about 26 minutes per channel. | After the field tests | Measure which per-file step costs most (create, write, flush, set the time, check the name, rename) before changing the copy engine. | NAS field test, 2026-10-05 |

## Closed items

Decided items are in `docs/DECISIONS.md` (D1–D76). The M0 review table in
[reports/M0.md](reports/M0.md) shows which review items each decision closed.

| ID | Item | Closed by |
| --- | --- | --- |
| O2 | How a local folder splits into `storage_root` and `rel_path` | D14 (2026-10-02) |
| O3 | Mapped drives to UNC; no list of NAS roots in the config | D14 (2026-10-02) |
| O4 | Scanner edge cases | D11 (2026-10-02) |
| O5 | Gap tolerance with fractional timestamps | D12 (2026-10-02) |
| O14 | Edit mode: confirming a rescan that changes the channel set | D16 (2026-10-02) |
| O23 | Logging works on any folder, local or on the NAS | D18 (2026-10-02) |
| O24 | A last file without IQ data | D13 (2026-10-02) |
| O29 | Creating a new database from the Settings tab | D30 (2026-10-02) |
| O18 | Writing `config.toml` | D31 (2026-10-02) |
| O27 | Name of the Settings milestone | D32 (2026-10-02) |
| O28 | When Settings changes apply | D33 (2026-10-02) |
| O30 | Which keys the Settings tab shows | D34 (2026-10-02) |
| O31 | Backup of `config.toml` on Save | D35 (2026-10-02) |
| O15 | Coverage highlight threshold | D39 (2026-10-03) |
| O16 | `list_recordings` at the size of the catalogue | D40 (2026-10-03) |
| O17 | Deleting a wrongly logged recording in the GUI | D41 (2026-10-03) |
| O13 | Save scripts, run scripts, or both | D48 (2026-10-03): the app copies files itself |
| O6 | Which files a time range includes | D49 (2026-10-03) |
| O7 | Archiving a time range or channel subset | D50 (2026-10-03) |
| O8 | "Destination empty or new" blocks resuming and second ranges | D51 (2026-10-03) |
| O9 | Deletion record and per-file manifest | D52 (2026-10-03) |
| O32 | Real file names for transfers | D53 (2026-10-03) |
| O36 | A check straight after a copy may read from the PC's cache | D55 (2026-10-03) |
| O11 | "Verify against source" for recordings logged in place on the NAS | D56 (2026-10-03) |
| O34 | Diagnostics and the test set in the packaged app | D57 (2026-10-03) |
| O35 | Files copied at once, and the flush, as settings | D58 (2026-10-03) |
| O1 | Time input in the Archive / copy tab | D59 (2026-10-03) |
| O10 | Copy-to-PC destination layout | D60 (2026-10-03) |
| O25 | One capture logged twice | D61 (2026-10-03) |
| O12 | `finish_transfer` replaces `notes` | D62 (2026-10-03) |
| O33 | Long paths in the packaged app (`longPathAware`) | D65 (2026-10-04) |
| O21 | Scratch database on the NAS: UNC open, writes, locking with two PCs | Passed on the NAS: `create` and `check` on 2026-10-05, locking from two PCs on 2026-10-09 (Milestone 8) |

## Pending checks for the user

- D75 on the NAS, at the next visit or in the pilot: an archive from a laptop passes
  as before, and so do its Check before delete and Delete laptop copy; an archive of a
  folder logged under one NAS name to the same folder under another name (host name
  and IP address) is refused at the preview.

The Milestone 1 exe check (`dist/smoke-2/`) was confirmed by the user on 2026-10-02.
The Milestone 6 manual test on this PC passed on 2026-10-04. The release review ran on
2026-10-11 ([reports/2026-10-11-release-review.md](reports/2026-10-11-release-review.md)).
The checks of D73, D75 and D76 with `dist/m8-2` passed on this PC on 2026-10-12
([reports/M8.md](reports/M8.md), part 2).

## Files for the user to remove

Agents may not delete files. These are gitignored and safe to remove by hand:

- `dist/smoke-1/`, `dist/smoke-2/`
- `build/work-smoke-1/`, `build/work-smoke-2/`
- `build/smoke-1-build.log`, `build/smoke-2-build.log`
- `build/spec-removed-sections.md`
- `fixtures_out/demo/`, `fixtures_out/m2-demo/`, `fixtures_out/m2-big/`
- `dev/test.db` and `dev/m3.db`. Both were made before D64 and D73, so the app
  refuses them as older versions. O21 is closed.
- After the Milestone 3 manual tests: `fixtures_out/m3-manual/`.
- `dev/m3a-shots/` (Settings tab screenshots), and `dev/m3a-manual/` after the
  Milestone 3a manual tests.
- `dev/m4-bench/` (timing script and two synthetic databases, 2.5 MB and 25.5 MB),
  `dev/m4-shots/` (Viewer and Settings screenshots), and `dev/m4-manual/` after the
  Milestone 4 manual tests.
- `dev/m5-copy-check/` (local copy timings and the fsync probe, about 4.8 GB).
- `dev/m5-testset-quick/` (the quick test set, 67.8 MB).
- `dist/m6-1/`, `dist/m6-2/` (103 MB each, superseded by `dist/m6-3`),
  `build/work-m6-1/`, `build/work-m6-2/`, `build/m6-1-build.log`,
  `build/m6-2-build.log`; after the NAS field test also `dist/m6-3/`,
  `build/work-m6-3/` and `build/m6-3-build.log`.
- `dev/m6-shots/` (screenshots and `shots.py`, 1.3 MB) and `dev/m6-exe-check/`
  (output of the packaged diagnostics, 81 MB).
- `dev/m6-manual/` (the manual test on this PC passed on 2026-10-04).
- `dist/m7-1/`, `build/work-m7-1/` and `build/m7-1-build.log`, and `dev/m7-legacy/`
  (the synthetic legacy file, its import, the script that made it, an Edge profile
  and a screenshot) and `dev/m7-checklist/` (failed render attempts).
- `dist/m7-2/`, `build/work-m7-2/` and `build/m7-2-build.log`. Keep
  `dist/m7-2/IQDataManager/field-test/` elsewhere if the logs are wanted; they hold
  the NAS address, so they stay out of the repository.
- `dist/m7-3/`, `build/work-m7-3/` and `build/m7-3-build.log` (superseded by
  `dist/m7-4`, built from `main`).
- `dist/m7-4/`, `build/work-m7-4/` and `build/m7-4-build.log`, after the second NAS
  visit, which used them (superseded by `dist/m8-1`).
- `dist/m8-1/`, `build/work-m8-1/` and `build/m8-1-build.log` (superseded by
  `dist/m8-2`).
- After the release review (2026-10-11): `dist/review-1/`, `build/work-review-1/`,
  `build/review-1-build.log` and `dev/review/` (reproductions, screenshots and a
  scratch database). The pytest folders under `%TEMP%\pytest-of-Perry\` hold
  directory junctions from the review and from the D75 tests. Remove each as a link,
  so that its target is not touched.
- `dev/scratch.db`, made to check the README's run commands.
- `src/iqdm/transfer/scripts/`, an empty package left from before D48. No module
  imports it. This one is in git, so remove it with a commit.
- After the NAS field test: the test set on the laptop and the folders the test
  writes on the NAS.
- Outside the repository: `claude_pw.py` in `%TEMP%`, and the session's scratch
  folders under `%TEMP%\claude\` (Milestone 3 report, issue 5).
- `build/pyinstaller-cache/` can stay; it speeds up later builds.

## Notes for agents

These come from the safety configuration and from experience in this repository.

- **The safety hook blocks Write and Edit outside the repository.** That includes
  Claude Code plan files, the memory folder and the session scratchpad. Present plans
  in chat; ExitPlanMode works without a plan file. Keep anything that must outlast a
  session in `docs/`. Put screenshot, timing and probe scripts under `dev/`, which is
  gitignored. The user removes old `dev/` folders, so do not rely on earlier scripts
  being there.
- **The hook scans the full text of shell commands.** Words such as `rm`, `rmtree`,
  `robocopy`, `.unlink(`, `os.remove`, `format x:` and `shutdown` block the command,
  even inside a commit message or a heredoc. A UNC path also blocks it: two
  backslashes, a name and a backslash at the start of a word, or the same with
  escaped backslashes. The user narrowed this pattern on 2026-10-02, so a backslash
  pair inside a word (such as `%APPDATA%\\IQDataManager`) no longer blocks. Commit
  `77ed32c` holds that change. A text search for such a word in the shell is blocked
  too. The user approved the Grep tool for those searches on 2026-10-03.
- **Write and change file content only with the Write and Edit tools.** Do not use
  heredocs, `cat >>`, `sed -i` or `python -` scripts for file content, even where the
  harness suggests shell edits. For a rename across a file, use Edit with
  `replace_all`. The hook checks the target path of Write and Edit and does not read
  their content, so docs, code and tests can hold example UNC strings.
- **Large tables sort in their own model.** A `QSortFilterProxyModel` over a Python
  model calls `data()` for every comparison: 0.5 s for 5,000 rows on the main thread
  in Milestone 4. See `gui/widgets/recording_model.py` (D40).
- **GUI tests share one `QApplication`.** A test that runs the event loop and quits it
  must not leave a quit behind: see the `smoke_app` fixture in
  `tests/test_app_smoke.py`. Wait for a `TaskRunner` with
  `qtbot.waitUntil(lambda: not runner.busy)`. The Viewer, Log and Settings tabs each
  start database reads when they are built, so a main-window test waits for all three
  runners (`wait_window` in `tests/test_app_smoke.py`).
- **Ruff reports a string split over several lines at its first line.** A `# noqa`
  for such a string goes on that first line, for example S608 on the dynamic SQL in
  `repository.list_recordings()`.
- **Agents may not edit `.claude/`.** The `PowerShell` tool is denied; use the Bash
  tool (Git Bash).
- **Install packages with the literal command `pip install --no-cache-dir ...`.** The
  project's ask rule only matches that prefix. `python -m pip install` would get past
  it.
- **PyInstaller builds go into new folders** (`dist/smoke-<n>`, `build/work-smoke-<n>`)
  with `PYINSTALLER_CONFIG_DIR=build/pyinstaller-cache`. Never use `--noconfirm` or
  `--clean`. See `README.md` and D8.
- **Git:** one branch per milestone. Stage files by explicit path; never `git add -A`.
  Merging, pushing and any git command other than `status`, `diff`, `log`, `add` and
  `commit` need the user's approval.
- **Line endings:** `core.autocrlf=true`, so commits print CRLF warnings. They are
  harmless.
- **Shell commands** must not leave a command waiting on standard input. A stray
  `cat > file` hung a command in Milestone 2 and left an empty file behind.
- **Tests** write under pytest's `tmp_path`, which is in `%TEMP%`. The fixture
  generator, `tools/make_fixtures.py`, is importable in tests as `make_fixtures`.
  The `db_path` fixture gives a fresh database. `recording_from(info)` in
  `tests/conftest.py` turns a generated recording into a matching `Recording`.
- **Transfer tests** copy, verify and delete real files, always under `tmp_path`. A
  "NAS" in them is a `tmp_path` folder passed to `Config(nas_roots=...)` directly;
  `resolve_drive=None` and a stubbed `disk_usage` keep the tests off real drives. See
  `tests/test_operations.py`.
- **`QComboBox` keeps a `StrEnum` as plain text.** `currentData()` returns `'none'`,
  not `HashMode.NONE`, so `is` comparisons fail. Turn it back, as
  `TransferTab.hash_mode()` does.
- **The scripts in `tools/` replace themselves with the package module** in
  `sys.modules`. `import make_fixtures` in a test gives `iqdm.diagnostics.fixtures`,
  so monkeypatching either name changes the same module.
- **A widget never shown reports `isVisible()` False.** GUI tests check `isHidden()`.
- **Code that deletes or overwrites a file** is listed in the Milestone 6 report
  (earlier: Milestone 5), section "Code paths that delete or overwrite a file".
  Update that list in the milestone report when such code changes, as
  `docs/KICKOFF.md` asks for Milestones 5 and 6.
- **A test module must not import a class named `Test...`.** Pytest tries to collect
  it, and a dataclass then raises a collection warning, which the configuration
  turns into an error. Tool classes are named accordingly (`SetSizes` in
  `tools/make_nas_testset.py`).
- **Reports:** every milestone ends with a report in `docs/reports/` that follows
  `docs/REPORT_TEMPLATE.md`, and an update to this file.
- **`ruff format` only on the files you change.** Several files on `main` are not in
  `ruff format` style, and the project checks only `ruff check`. Running the formatter
  on a whole folder rewrapped unrelated code three times in Milestone 3.
- **A Windows share of a local folder** can stand in for the NAS in a manual test,
  because NAS locations must be UNC paths. Check before delete fails through such a
  share with WinError 87 (2026-10-12): Windows refuses reads past the cache when a PC
  serves a share to itself. Test the delete on the real NAS.
- **Screenshots of the GUI** render offscreen with the light palette. Set
  `QT_QPA_FONTDIR=C:/Windows/Fonts` for readable text. The user runs Windows in dark
  mode, so render with a dark palette too: set the `Base`, `Text`, `Window`,
  `WindowText`, `Button`, `ButtonText` and `PlaceholderText` roles, call
  `app.setPalette()` before the widget is built, and save `widget.grab()`. The
  offscreen style draws disabled buttons nearly like enabled ones; check button states
  in tests.
