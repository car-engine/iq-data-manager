# Project status

Read this file at the start of every session, after `CLAUDE.md`. Update it at the end
of every milestone and after any other significant work, in the same commit as the
report. Last updated: 2026-10-02.

## Current state

- Milestone 2 (Scanner) is complete on branch `m2-scanner` and waits for the user's
  merge approval. Report: [reports/M2.md](reports/M2.md).
- 301 tests pass and 1 skips (symbolic links need a privilege this account lacks).
  `ruff check` is clean.
- Next: merge `m2-scanner`, then Milestone 3 (Log tab). O21 is due before
  Milestone 3.

## Milestones

Scope of each milestone: `docs/SPEC.md` section 12.

| Milestone | Status | Branch | Commits | Report |
| --- | --- | --- | --- | --- |
| 0. Scaffold | Done | `main` | `dac3d8f`–`ccf08f3` | [M0](reports/M0.md) |
| 1. Database layer | Done, merged | `m1-database` | `d2e11b3`–`f832167`, `48d7749` (handoff documents), plus the commit that records the merge | [M1](reports/M1.md) |
| 2. Scanner | Done, not merged | `m2-scanner` | `fa39b82`–`6402af7`, plus the commit that adds the report | [M2](reports/M2.md) |
| 3. Log tab | Not started | | | |
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
| O1 | Display time zone. The Viewer shows "start (UTC+8)", CLAUDE.md forbids local time, the Move / copy tab takes UTC input. | 3, 4, 6 | Store UTC. Config key `display_utc_offset_hours = 8`. Every displayed time shows its offset. Input fields stay UTC. | M0 review 9 |
| O2 | How a local folder splits into `storage_root` and `rel_path` | 3 | Local: root = parent folder, `rel_path` = folder name. NAS: root = configured NAS root, `rel_path` = remainder. | M0 review 10 |
| O3 | Mapped drives to UNC; no list of NAS roots in the config | 3 | Resolve mapped drives with `WNetGetConnectionW` through `ctypes`. Add a `nas_roots` config list. | M0 review 11 |
| O6 | Which files a time range includes | 5 | A file at time `t` is in range when `start <= t < end`. | M0 review 18 |
| O7 | Archiving a time range or channel subset would point the DB at a partial copy | 5, 6 | "Archive to NAS" accepts only a whole recording with all channels. | M0 review 13 |
| O8 | "Destination empty or new" blocks resuming a copy and copying a second range into the same folder | 5 | Keep for moves. For copies, allow a non-empty destination when none of the target files exist there. | M0 review 14 |
| O9 | Structured deletion record and per-file verification manifest for `delete.py` | 5 | Reconsider a `'delete'` operation with `parent_id`, a DB trigger requiring a passed move, and `manifest_path` (proposed in Milestone 1; the user deferred them). | M0 review 3, 4; D5 |
| O10 | Copy-to-PC destination layout: keep `rel_path` under `default_local_copy_root`, or a folder the user picks | 6 | None yet | M0 review 19 |
| O11 | "Verify against source" for recordings logged in place on the NAS, and how a later verification clears the unverified mark | 6 | None yet | D2 |
| O12 | `finish_transfer` replaces `notes`; source deletion is recorded in `notes` | 6 | Add to the existing text instead of replacing it. | M1 review |
| O13 | The app can both save scripts and run them. If the user prefers "generate only", drop the run path in Milestone 6 and keep verification as a "Check" action. | 6 | Save and run. | Former SPEC section 13 |
| O14 | Edit mode: the GUI must confirm before applying a rescan that changes the channel set | 3 | Ask, then call `update_recording(..., allow_channel_removal=True)`. | M0 review 20; D7 |
| O15 | Coverage highlight threshold of 99% | 4 | 99%, as a config key. | Former SPEC section 13 |
| O16 | `list_recordings` loads every channel in one query; not measured beyond thousands of recordings | 4 | Revisit with the Viewer filters. | M1 review |
| O17 | No way to delete a wrongly logged recording in the GUI (`repository.delete_recording` exists) | 4 | Out of scope for v1. | M0 review 23 |
| O18 | Missing config keys (data-file extensions, coverage threshold, free-space margin, NAS roots, display offset). `tomllib` only reads TOML. | 7 (NAS roots in 3) | Hand-written writer for flat keys, or `tomli-w` as a new dependency (needs approval). | M0 review 21 |
| O19 | GUI for the confirmed "Upgrade database" action | 7 | Settings dialog or startup prompt. | D6 |
| O20 | Frozen copy of the version 1 schema for testing future migrations | 7 | Snapshot `schema.sql` as `tests/schemas/v1.sql` when the first real database is created. | D4 |
| O21 | Test on a scratch database on the NAS: UNC open, writes, locking with two PCs | User, before Milestone 3 | The agent writes a script that takes the path as an argument. The user runs it. | M1 check D |
| O22 | SQLite on SMB: scheduled backup of the catalogue outside the app | User | None yet | M0 review 24 |
| O23 | Logging works on any folder, local or on the NAS; scanning NAS folders is slower | 3 | Keep. | Former SPEC section 13 |

## Closed items

Decided items are in `docs/DECISIONS.md` (D1–D13). The M0 review table in
[reports/M0.md](reports/M0.md) shows which review items each decision closed.

| ID | Item | Closed by |
| --- | --- | --- |
| O4 | Scanner edge cases | D11 (2026-10-02) |
| O5 | Gap tolerance with fractional timestamps | D12 (2026-10-02) |
| O24 | A last file without IQ data | D13 (2026-10-02) |

## Pending checks for the user

- O21 before Milestone 3.

The Milestone 1 exe check (`dist/smoke-2/`) was confirmed by the user on 2026-10-02.

## Files for the user to remove

Agents may not delete files. These are gitignored and safe to remove by hand:

- `dist/smoke-1/`, `dist/smoke-2/`
- `build/work-smoke-1/`, `build/work-smoke-2/`
- `build/smoke-1-build.log`, `build/smoke-2-build.log`
- `build/spec-removed-sections.md`
- `fixtures_out/demo/`, `fixtures_out/m2-demo/`, `fixtures_out/m2-big/`
- `fixtures_out_mut_conftest.py` in the repository root (empty; created by mistake in
  Milestone 2)
- `build/pyinstaller-cache/` can stay; it speeds up later builds.

## Notes for agents

These come from the safety configuration and from experience in this repository.

- **The safety hook blocks every write outside the repository.** That includes Claude
  Code plan files and the memory folder. Present plans in chat, and keep anything
  that must outlast a session in `docs/`.
- **The hook scans the full text of shell commands.** Words such as `rm`, `rmtree`,
  `robocopy`, `.unlink(`, `os.remove`, `format x:` and `shutdown` block the command,
  even inside a commit message or a heredoc. Write such text with the file tools
  instead.
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
