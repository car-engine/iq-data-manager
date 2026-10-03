# Project status

Read this file at the start of every session, after `CLAUDE.md`. Update it at the end
of every milestone and after any other significant work, in the same commit as the
report. Last updated: 2026-10-04 (Milestone 6 built; NAS field test pending).

## Current state

- Milestones 0 to 5 are merged into `main` and pushed. On `main`, 1,202 tests pass and
  4 skip.
- **Milestone 6, Archive / copy tab, is built on branch `m6-move-copy-tab`** and not
  merged. Report: [reports/M6.md](reports/M6.md). 1,410 tests pass and 4 skip on the
  branch; three skips need the symbolic-link privilege, the other runs only off
  Windows. `ruff check` is clean.
- **The milestone ends with the NAS field test (D54)**, which the user runs with
  `dist/m6-3/IQDataManager/` (built from `47a7f06`). The steps are in the report.
  `dist/m6-1` and `dist/m6-2` are older and lack fixes; do not take them to the NAS.
- D55–D62 closed O36, O11, O34, O35, O1, O10, O25 and O12. D63 hashes skipped files
  when a transfer resumes. D64 renamed the operation "move" to "archive" everywhere.
- Scratch databases made before D64, such as `dev/test.db` and `dev/m3.db`, refuse
  archive rows. Create a new one with `tools/db_check.py create` (or
  `IQDataManager-check.exe db-check create`).
- The diagnostics live in `src/iqdm/diagnostics/`; `tools/` holds wrappers, and the
  build holds the console program `IQDataManager-check.exe` (D57).
- All text on screen follows CLAUDE.md, section "User-facing text" (D38).
  `tests/test_user_text.py` checks the Viewer, Log, Settings and Archive / copy tabs.
- The NAS part of O21 is still open. The local part is done
  ([reports/2026-10-02-db-check.md](reports/2026-10-02-db-check.md)).

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
| 6. Archive / copy tab | Built, NAS field test pending, not merged | `m6-move-copy-tab` | `7f1273b`–`95c9256`, plus the commit of the report | [M6](reports/M6.md) |
| 7. Packaging and migration | Not started | | | |

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
| O20 | Frozen copy of the version 1 schema for testing future migrations | 7 | Snapshot `schema.sql` as `tests/schemas/v1.sql` when the first real database is created. | D4 |
| O21 | Test on a scratch database on the NAS: UNC open, writes, locking with two PCs | User, before the app writes to a real database on the NAS | `tools/db_check.py` exists and passed on this PC, including locking between two processes. The user runs it on the NAS from two PCs. The user started Milestone 3 before this test on 2026-10-02. | M1 check D |
| O22 | SQLite on SMB: scheduled backup of the catalogue outside the app | User | None yet | M0 review 24 |
| O33 | Long paths in the packaged app. `transfer/pathcheck.py` allows paths above the Windows limits when long paths are enabled in the registry. The executable also needs a manifest that declares `longPathAware`. | 7 | Check the PyInstaller build's manifest. Until then, keep destination paths short. | Milestone 5 |

## Closed items

Decided items are in `docs/DECISIONS.md` (D1–D64). The M0 review table in
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

## Pending checks for the user

- A manual test of the Archive / copy tab on this PC with the quick test set. Steps in
  [reports/M6.md](reports/M6.md), "Manual test on this PC".
- The NAS field test (D54) with `dist/m6-3/IQDataManager/`, including O21 (`db-check`
  `check`, `hold` and `write` on a scratch database on the NAS, from two PCs). Steps in
  [reports/M6.md](reports/M6.md), "NAS field test". O21 must pass before the app
  writes to a real database on the NAS.

The Milestone 1 exe check (`dist/smoke-2/`) was confirmed by the user on 2026-10-02.

## Files for the user to remove

Agents may not delete files. These are gitignored and safe to remove by hand:

- `dist/smoke-1/`, `dist/smoke-2/`
- `build/work-smoke-1/`, `build/work-smoke-2/`
- `build/smoke-1-build.log`, `build/smoke-2-build.log`
- `build/spec-removed-sections.md`
- `fixtures_out/demo/`, `fixtures_out/m2-demo/`, `fixtures_out/m2-big/`
- `dev/test.db` is the user's scratch database for O21. Move it out of the repository
  before the NAS test.
- After the Milestone 3 manual tests: `dev/m3.db` and `fixtures_out/m3-manual/`.
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
- `dev/test.db` and `dev/m3.db` were made before D64 and refuse archive rows.
- After the tests: `dev/m6-manual/`, the test set on the laptop and the folders the
  test writes on the NAS.
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
- **Screenshots of the GUI** render offscreen with the light palette. Set
  `QT_QPA_FONTDIR=C:/Windows/Fonts` for readable text. The user runs Windows in dark
  mode, so render with a dark palette too: set the `Base`, `Text`, `Window`,
  `WindowText`, `Button`, `ButtonText` and `PlaceholderText` roles, call
  `app.setPalette()` before the widget is built, and save `widget.grab()`. The
  offscreen style draws disabled buttons nearly like enabled ones; check button states
  in tests.
