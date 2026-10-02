# Project status

Read this file at the start of every session, after `CLAUDE.md`. Update it at the end
of every milestone and after any other significant work, in the same commit as the
report. Last updated: 2026-10-03 (Milestone 4 merged).

## Current state

- Milestone 4 (Viewer tab) is merged into `main` (fast-forward, 2026-10-03) and
  pushed. Report: [reports/M4.md](reports/M4.md). Decisions D39–D47. The user ran
  the manual tests on 2026-10-03, and they passed.
- 918 tests pass and 2 skip on `main`. One skip needs the symbolic-link privilege;
  the other runs only off Windows. `ruff check` is clean.
- **Next: Milestone 5, Transfer core**, on a new branch `m5-transfer-core`. Open
  items to raise in its plan: O6, O7, O8, O9 and O32.
- All text on screen follows CLAUDE.md, section "User-facing text" (D38).
  `tests/test_user_text.py` checks the Viewer, Log and Settings tabs.
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
| 5. Transfer core | Not started | | | |
| 6. Move / copy tab | Not started | | | |
| 7. Packaging and migration | Not started | | | |

Commits between the milestones on `main`: `814417c` (decisions D1–D3 in the spec),
`89e94ac` (the user's PowerShell deny rule in `.claude/settings.json`), `6028895` and
`68fb49c` (D29, D30), `257244c` (documentation review) and `77ed32c` (the user's
narrower UNC pattern in the safety hook).

## Open items

Questions and known gaps that are not yet decided. The default is what an agent
proposes unless the user decides otherwise. Raise each item in the plan for its
milestone. When it is decided, record it in `docs/DECISIONS.md`, update `SPEC.md`,
and move it to "Closed items" below. "M0 review <n>" refers to the table in
[reports/M0.md](reports/M0.md).

| ID | Item | Milestone | Proposed default | Origin |
| --- | --- | --- | --- | --- |
| O1 | Time input in the Move / copy tab. Displayed times follow `display_utc_offset_hours` (D24, default 8). | 6 | Input fields stay UTC and say so. | M0 review 9 |
| O6 | Which files a time range includes | 5 | A file at time `t` is in range when `start <= t < end`. | M0 review 18 |
| O7 | Archiving a time range or channel subset would point the DB at a partial copy | 5, 6 | "Archive to NAS" accepts only a whole recording with all channels. | M0 review 13 |
| O8 | "Destination empty or new" blocks resuming a copy and copying a second range into the same folder | 5 | Keep for moves. For copies, allow a non-empty destination when none of the target files exist there. | M0 review 14 |
| O9 | Structured deletion record and per-file verification manifest for `delete.py` | 5 | Reconsider a `'delete'` operation with `parent_id`, a DB trigger requiring a passed move, and `manifest_path` (proposed in Milestone 1; the user deferred them). | M0 review 3, 4; D5 |
| O10 | Copy-to-PC destination layout: keep `rel_path` under `default_local_copy_root`, or a folder the user picks | 6 | None yet | M0 review 19 |
| O11 | "Verify against source" for recordings logged in place on the NAS, and how a later verification clears the unverified mark. The Viewer shows the mark while the D2 row exists (D44). | 6 | None yet | D2 |
| O12 | `finish_transfer` replaces `notes`; source deletion is recorded in `notes` | 6 | Add to the existing text instead of replacing it. | M1 review |
| O13 | The app can both save scripts and run them. If the user prefers "generate only", drop the run path in Milestone 6 and keep verification as a "Check" action. | 6 | Save and run. | Former SPEC section 13 |
| O19 | GUI for the confirmed "Upgrade database" action | With the first real schema migration | A button in the Settings tab's database section, shown only when the schema needs an upgrade, plus a startup message that points to it. Deferred by D30; until then an older database gives a red status line (D38). | D6; D29; D30 |
| O20 | Frozen copy of the version 1 schema for testing future migrations | 7 | Snapshot `schema.sql` as `tests/schemas/v1.sql` when the first real database is created. | D4 |
| O21 | Test on a scratch database on the NAS: UNC open, writes, locking with two PCs | User, before the app writes to a real database on the NAS | `tools/db_check.py` exists and passed on this PC, including locking between two processes. The user runs it on the NAS from two PCs. The user started Milestone 3 before this test on 2026-10-02. | M1 check D |
| O22 | SQLite on SMB: scheduled backup of the catalogue outside the app | User | None yet | M0 review 24 |
| O25 | One capture logged twice. A recording copied to the NAS by hand and logged there (D2) can also be logged from its laptop folder. The two locations differ, so `UNIQUE (storage_root, rel_path)` accepts both. | 6 (with O11) | The Log tab reports information when another recording has the same start, end and channel indices. | User question, 2026-10-02 |
| O32 | Real file names for transfers. The database does not store the file extension, and SPEC section 8 writes manifests as `<timestamp>.dat`. | 5 | Store the extension per channel when a recording is logged (a schema change while `schema.sql` is still edited in place, D4). The fallback is a rescan of the source folder before each transfer. | D30 |

## Closed items

Decided items are in `docs/DECISIONS.md` (D1–D47). The M0 review table in
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

## Pending checks for the user

- O21 before the app writes to a real database on the NAS: run `tools/db_check.py`
  `check`, `hold` and `write` on a scratch database on the NAS, with `hold` and
  `write` on two PCs. Steps are in
  [reports/2026-10-02-db-check.md](reports/2026-10-02-db-check.md).

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
- Outside the repository: `claude_pw.py` in `%TEMP%`, and the session's scratch
  folders under `%TEMP%\claude\` (Milestone 3 report, issue 5).
- `build/pyinstaller-cache/` can stay; it speeds up later builds.

## Notes for agents

These come from the safety configuration and from experience in this repository.

- **The safety hook blocks Write and Edit outside the repository.** That includes
  Claude Code plan files, the memory folder and the session scratchpad. Present plans
  in chat; ExitPlanMode works without a plan file. Keep anything that must outlast a
  session in `docs/`. Put screenshot and probe scripts under `dev/`, which is
  gitignored (example: `dev/m3a-shots/shot.py`).
- **The hook scans the full text of shell commands.** Words such as `rm`, `rmtree`,
  `robocopy`, `.unlink(`, `os.remove`, `format x:` and `shutdown` block the command,
  even inside a commit message or a heredoc. A UNC path also blocks it: two
  backslashes, a name and a backslash at the start of a word, or the same with
  escaped backslashes. The user narrowed this pattern on 2026-10-02, so a backslash
  pair inside a word (such as `%APPDATA%\\IQDataManager`) no longer blocks. Commit
  `77ed32c` holds that change.
- **Write and change file content only with the Write and Edit tools.** Do not use
  heredocs, `cat >>` or `python -` scripts for file content. The hook checks the
  target path of Write and Edit and does not read their content, so docs, code and
  tests can hold example UNC strings.
- **Large tables sort in their own model.** A `QSortFilterProxyModel` over a Python
  model calls `data()` for every comparison: 0.5 s for 5,000 rows on the main thread
  in Milestone 4. See `gui/widgets/recording_model.py` (D40).
- **GUI tests share one `QApplication`.** A test that runs the event loop and quits it
  must not leave a quit behind: see the `smoke_app` fixture in
  `tests/test_app_smoke.py`. Wait for a `TaskRunner` with
  `qtbot.waitUntil(lambda: not runner.busy)`.
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
  The `db_path` fixture gives a fresh database.
- **Reports:** every milestone ends with a report in `docs/reports/` that follows
  `docs/REPORT_TEMPLATE.md`, and an update to this file.
- **`ruff format` only on the files you change.** Several files on `main` are not in
  `ruff format` style, and the project checks only `ruff check`. Running the formatter
  on a whole folder rewrapped unrelated code three times in Milestone 3.
- **Screenshots of the GUI** render offscreen with the light palette. Set
  `QT_QPA_FONTDIR=C:/Windows/Fonts` for readable text. The user runs Windows in dark
  mode, so render with a dark palette too (`dev/m3a-shots/shot.py` does both). The
  offscreen style draws disabled buttons nearly like enabled ones; check button states
  in tests.
