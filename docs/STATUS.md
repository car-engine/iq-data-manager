# Project status

Read this file at the start of every session, after `CLAUDE.md`. Update it at the end
of every milestone and after any other significant work, in the same commit as the
report. Last updated: 2026-10-02.

## Current state

- Milestone 2 (Scanner) is complete and merged into `main` (fast-forward,
  2026-10-02). Report: [reports/M2.md](reports/M2.md).
- 322 tests pass and 1 skips on `main` (symbolic links need a privilege this account
  lacks). `ruff check` is clean.
- Milestone 3 (Log tab) is complete on branch `m3-log-tab` and not merged. Report:
  [reports/M3.md](reports/M3.md). On the branch, 599 tests pass and 2 skip, and
  `ruff check` is clean.
- After a first look at the tab, the user added D21 (fs from the file size), D22
  (file duration from the file names, coverage above 100 % as an error) and D23
  (to-do items in the checklist). Issue 1 of the report is closed by D20.
- After the first manual test, the user added D24 (times at UTC+8 by default,
  replaces D17) and D25 (fs with units, Hz by default), plus a save pop-up and grey
  read-only fields. D26: a new folder resets the file duration, the format fields,
  the channel rows and the RF chain rows.
- Before the merge, the user runs the manual test set in `fixtures_out/m3-manual/`
  with `dev/m3.db`. The steps are in the Milestone 3 report.
- The user changed the UNC pattern in `.claude/hooks/block_destructive.py`. The
  change is not committed; agents may not commit `.claude/`.
- The user chose to start Milestone 3 before the NAS part of O21. The local part is
  done ([reports/2026-10-02-db-check.md](reports/2026-10-02-db-check.md)).
- Next: Milestone 4 (Viewer tab), after the merge.

## Milestones

Scope of each milestone: `docs/SPEC.md` section 12.

| Milestone | Status | Branch | Commits | Report |
| --- | --- | --- | --- | --- |
| 0. Scaffold | Done | `main` | `dac3d8f`–`ccf08f3` | [M0](reports/M0.md) |
| 1. Database layer | Done, merged | `m1-database` | `d2e11b3`–`f832167`, `48d7749` (handoff documents), plus the commit that records the merge | [M1](reports/M1.md) |
| 2. Scanner | Done, merged | `m2-scanner` | `fa39b82`–`d764074`, plus the commit that records the merge | [M2](reports/M2.md) |
| 3. Log tab | Done, not merged | `m3-log-tab` | `0569068`–`61c5713`, plus the commit that brings the report up to date | [M3](reports/M3.md) |
| 4. Viewer tab | Not started | | | |
| 5. Transfer core | Not started | | | |
| 6. Move / copy tab | Not started | | | |
| 7. Packaging and migration | Not started | | | |

Commits between the milestones on `main`: `814417c` (decisions D1–D3 in the spec) and
`89e94ac` (the user's PowerShell deny rule in `.claude/settings.json`).

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
| O11 | "Verify against source" for recordings logged in place on the NAS, and how a later verification clears the unverified mark | 6 | None yet | D2 |
| O12 | `finish_transfer` replaces `notes`; source deletion is recorded in `notes` | 6 | Add to the existing text instead of replacing it. | M1 review |
| O13 | The app can both save scripts and run them. If the user prefers "generate only", drop the run path in Milestone 6 and keep verification as a "Check" action. | 6 | Save and run. | Former SPEC section 13 |
| O15 | Coverage highlight threshold of 99% | 4 | 99%, as a config key. | Former SPEC section 13 |
| O16 | `list_recordings` loads every channel in one query; not measured beyond thousands of recordings | 4 | Revisit with the Viewer filters. | M1 review |
| O17 | No way to delete a wrongly logged recording in the GUI (`repository.delete_recording` exists) | 4 | Out of scope for v1. | M0 review 23 |
| O18 | Missing config keys (data-file extensions, coverage threshold, free-space margin, display offset). `tomllib` only reads TOML. Milestone 3 reads the file and adds `nas_roots` (D15). | 7 | Hand-written writer for flat keys, or `tomli-w` as a new dependency (needs approval). | M0 review 21 |
| O19 | GUI for the confirmed "Upgrade database" action | 7 | Settings dialog or startup prompt. | D6 |
| O20 | Frozen copy of the version 1 schema for testing future migrations | 7 | Snapshot `schema.sql` as `tests/schemas/v1.sql` when the first real database is created. | D4 |
| O21 | Test on a scratch database on the NAS: UNC open, writes, locking with two PCs | User, before the app writes to a real database on the NAS | `tools/db_check.py` exists and passed on this PC, including locking between two processes. The user runs it on the NAS from two PCs. The user started Milestone 3 before this test on 2026-10-02. | M1 check D |
| O22 | SQLite on SMB: scheduled backup of the catalogue outside the app | User | None yet | M0 review 24 |
| O25 | One capture logged twice. A recording copied to the NAS by hand and logged there (D2) can also be logged from its laptop folder. The two locations differ, so `UNIQUE (storage_root, rel_path)` accepts both. | 6 (with O11) | The Log tab reports information when another recording has the same start, end and channel indices. | User question, 2026-10-02 |

## Closed items

Decided items are in `docs/DECISIONS.md` (D1–D26). The M0 review table in
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
- Outside the repository: `claude_pw.py` in `%TEMP%`, and the session's scratch
  folders under `%TEMP%\claude\` (Milestone 3 report, issue 5).
- `build/pyinstaller-cache/` can stay; it speeds up later builds.

## Notes for agents

These come from the safety configuration and from experience in this repository.

- **The safety hook blocks every write outside the repository.** That includes Claude
  Code plan files and the memory folder. Present plans in chat, and keep anything
  that must outlast a session in `docs/`.
- **The hook scans the full text of shell commands.** Words such as `rm`, `rmtree`,
  `robocopy`, `.unlink(`, `os.remove`, `format x:` and `shutdown` block the command,
  even inside a commit message or a heredoc. A backslash pair followed by a name and
  a backslash looks like a UNC path and also blocks the command. That includes
  escaped backslashes in Python text.
- **Write and change file content only with the Write and Edit tools.** Do not use
  heredocs, `cat >>` or `python -` scripts for file content. The hook checks the
  target path of Write and Edit and does not read their content, so docs, code and
  tests can hold example UNC strings.
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
