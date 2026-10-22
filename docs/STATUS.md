# Project status

Read this file at the start of every session, after `CLAUDE.md` and
[HANDOFF.md](HANDOFF.md). Update it after every piece of work, in the same commit as
its report. Last updated: 2026-10-23 (O50, O39 and O51 done on their branches, not merged).

## Current state

- **Version 1.0.0 is released, and Milestones 0 to 8 are closed.** The tag `v1.0.0`
  is on `674434c`; `main` and the tag are pushed. The release build was made from
  the tag into `dist/release-1.0.0` on the development PC, with
  [RELEASE_NOTES.md](RELEASE_NOTES.md) in the program folder. At the close: 1,607
  tests pass and 4 skip (three need the symbolic-link privilege, one runs only off
  Windows); `ruff check` is clean. Report: [reports/M8.md](reports/M8.md), parts 1 to
  4.
- **Work after 1.0 comes from the team's feedback.** [HANDOFF.md](HANDOFF.md)
  describes how such work proceeds, the version and release steps, and the database
  format after 1.0. Start each piece of work from an open item below.
- **Version 1.1.0 is released** (2026-10-22). The tag `v1.1.0` is on `ed1afe8`; `main`
  and the tag are pushed. The plan, approved by the user on 2026-10-20, is in
  [PLAN.md](../PLAN.md): O20, O38, O43, O44 and O45 (with O41). On 2026-10-21 the user
  added O46 and O47 (the recorder's logs); the manual test of 2026-10-22 gave O48 and
  O49. All nine were merged into `main` as a fast-forward at `7e7bce2`, then
  `release-1.1.0` set the version and the release notes (`ed1afe8`). The build is
  `dist/release-1.1.0` (104 MB), made from `ed1afe8`: `--smoke-test` passed, both
  programs print 1.1.0, `IQDataManager-check.exe --help` lists its commands, both
  declare long-path support, and the shipped user guide, release notes and
  `defaults.example.toml` match their sources. At the release: 1,761 tests pass and 4
  skip; `ruff check` is clean. The user tests 1.1 in the field (pending checks below).
- **Version 1.1.1 is released** (2026-10-22). The tag `v1.1.1` is on `3108c63`;
  `main` and the tag are pushed. The review of 1.1.0
  ([reports/2026-10-22-review-1.1.0.md](reports/2026-10-22-review-1.1.0.md)) found ten
  faults, none a risk to data; all ten are fixed (D86, D87). The user's manual test
  passed on 2026-10-22. `main` was fast-forwarded to `log-fixes-1.1.1` at `3cedd34`,
  then `release-1.1.1` set the version and the release notes (`3108c63`). The build
  is `dist/release-1.1.1` (104 MB), made from `3108c63`: `--smoke-test` passed, both
  programs print 1.1.1, `IQDataManager-check.exe --help` lists its commands, both
  declare long-path support, and the shipped user guide, release notes and
  `defaults.example.toml` match their sources. At the release: 1,781 tests pass and 4
  skip; `ruff check` is clean.
- **The next work is version 1.2** (user, 2026-10-22), in this order: O50 (the band
  from fc), O39 (deleting an entry added by mistake, which changes D41), then a plan,
  discussed first, for O51 (logging several recordings with one set-up). The user
  approved the plan for O50 and O39 on 2026-10-23, and asked to discuss O51 again
  before any code for it. O50 is done on `band-from-fc` (D88) and O39 on
  `delete-entry` (D89). The user approved the plan for O51 on 2026-10-23; it is done
  on `log-several-folders` (D90). None is merged; the manual test of 1.2 comes
  first. A new
  session starts from the prompt "Version 1.2" in [KICKOFF.md](KICKOFF.md).
- **The 1.1 field checks passed** (user, 2026-10-22): the queue on the NAS with Pause
  and Start, a recorder recording logged, archived with its logs, checked and deleted
  from the laptop, several folders with a shared template, and the Viewer's filters
  and dark mode. The catalogue backup runs (O22 closed), and the team no longer uses
  the legacy logging scripts.
- **The version 1 schema is frozen** (O20 closed by D77). A change to `schema.sql`
  needs a numbered migration (HANDOFF.md, section 5).
- **The pilot passed** (user, 2026-10-20): the real catalogue exists, made with the
  1.0.0 build, and a real archive, its Check before delete and the delete of the
  laptop copy passed, with the D75 checks on the NAS. O22 and the cut-over from the
  legacy logging scripts are done (user, 2026-10-22).
- **Databases made before D73** (the trial catalogue of the second NAS visit, the
  scratch databases on the NAS, and `dev/test.db` and `dev/m3.db`) count as an older
  version, and the app refuses them. Make a new one with `tools/db_check.py create`
  or `IQDataManager-check.exe db-check create`.
- **The build in `dist/release-1.0.0`** still lists `FIELD_TEST_CHECKLIST.html` in its
  user guide; the user removed the file itself by hand. Builds after the tag ship and
  list neither. The checklist stays in `docs/` as a record of the second NAS visit.
- **History** is in the milestone reports. The NAS field test of 2026-10-05:
  [reports/M6.md](reports/M6.md). The second NAS visit of 2026-10-09 (O21 closed,
  D55 confirmed, the clock difference behind D74): [reports/M8.md](reports/M8.md),
  part 1. The release review and its fixes (D75, D76): M8.md, part 2. The
  `sed -i.bak '' /dev/null` slip of 2026-10-11, which changed nothing: M8.md, part 1.

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
| 8. Release 1.0 (D72) | Done, with gaps: O20 and the rollout moved to open items and the user (M8.md, part 4) | `m8-release` | `7bb2cca`–`9751b22` and `e6f0569` (part 1); `e016add` (review report)–`71ee3ed` (fixes and checks); `674434c` (1.0.0, tag `v1.0.0`); `4264491`–`3e9b1d0` (release records, the checklist out of the build); plus the commit of part 4. Merged into `main` as fast-forwards and pushed. | [M8](reports/M8.md) (parts 1 to 4), [release review](reports/2026-10-11-release-review.md) |

### Work after 1.0

One branch per piece of work (HANDOFF.md, section 3).

| Item | Status | Branch | Commits | Report |
| --- | --- | --- | --- | --- |
| O20, version 1 schema frozen (D77) | Done, not merged | `o20-freeze-schema-v1` | `a5e121a` (PLAN.md), `fee1198` | [2026-10-20-o20-freeze-schema](reports/2026-10-20-o20-freeze-schema.md) |
| O38, Viewer filters with several choices (D78) | Done, not merged | `viewer-multi-filter`, from `o20-freeze-schema-v1` | `1e212f6` | [2026-10-20-viewer-multi-filter](reports/2026-10-20-viewer-multi-filter.md) |
| O43, a new folder keeps the previous entry's fields (D79) | Done, not merged | `log-keep-fields`, from `viewer-multi-filter` | `336276a`, `2b49761` (SPEC) | [2026-10-20-log-keep-fields](reports/2026-10-20-log-keep-fields.md) |
| O44, Log tab templates (D80) | Done, not merged | `log-templates`, from `log-keep-fields` | `740fd54` | [2026-10-20-log-templates](reports/2026-10-20-log-templates.md) |
| O45 and O41, the queue (D81) | Done, not merged | `transfer-queue`, from `log-templates` | `e1f1147`, `c0252f9` (two fixes found while writing the manual checklist) | [2026-10-20-transfer-queue](reports/2026-10-20-transfer-queue.md) |
| O46, values from the recorder's log (D82) | Done, not merged | `recorder-log-fill`, from `transfer-queue` | `5f6831b` | [2026-10-21-recorder-log-fill](reports/2026-10-21-recorder-log-fill.md) |
| O47, log files travel with the recording (D83) | Done, not merged | `transfer-log-files`, from `recorder-log-fill` | `2574beb` | [2026-10-21-transfer-log-files](reports/2026-10-21-transfer-log-files.md) |
| O48, Log tab messages show their state (D84) | Done, not merged | `log-message-states`, from `transfer-log-files` | `9f37809` | [2026-10-22-log-message-states](reports/2026-10-22-log-message-states.md) |
| O49, an archive whose check is needed (D85) | Done, merged | `queue-check-state`, from `log-message-states` | `6ceb7ca`, `7e7bce2` (STATUS) | [2026-10-22-queue-check-state](reports/2026-10-22-queue-check-state.md) |
| Release 1.1.0 | Released: tag `v1.1.0`, pushed | `release-1.1.0`, from `main` at `7e7bce2` | `ed1afe8`, plus the commit of these records | This file and [RELEASE_NOTES.md](RELEASE_NOTES.md) |
| Review of 1.1.0 | Done, merged: ten findings, three to fix in 1.1.1, and finding 10 from the user | `review-1.1.0`, from `main` at `13af0b1` | `3e8f154`, `2a95784`; part 2 in `48804a2` | [2026-10-22-review-1.1.0](reports/2026-10-22-review-1.1.0.md) |
| Queue fixes for 1.1.1 (D86; review findings 1, 5, 6, 10) | Done, merged | `queue-fixes-1.1.1`, from `review-1.1.0` | `1f736ea`, `790177d` (report); `5bccf96` (Open in form, on `log-fixes-1.1.1`) | [2026-10-22-queue-fixes-1.1.1](reports/2026-10-22-queue-fixes-1.1.1.md) |
| Log tab fixes for 1.1.1 (D87; review findings 2, 3, 4, 7, 8) | Done, merged | `log-fixes-1.1.1`, from `queue-fixes-1.1.1` | `a9fa00e`, `58acd99` (report), `48804a2`–`3cedd34` (records and the manual test) | [2026-10-22-log-fixes-1.1.1](reports/2026-10-22-log-fixes-1.1.1.md) |
| Release 1.1.1 | Released: tag `v1.1.1`, pushed | `release-1.1.1`, from `main` at `3cedd34` | `3108c63`, plus the commit of these records | This file and [RELEASE_NOTES.md](RELEASE_NOTES.md) |
| O50, the band filled in from fc (D88) | Done, not merged | `band-from-fc`, from `main` at `9403f46` | `9bfba8c`, `12ae30a` (report) | [2026-10-23-band-from-fc](reports/2026-10-23-band-from-fc.md) |
| O39, deleting an entry added by mistake (D89) | Done, not merged | `delete-entry`, from `band-from-fc` at `12ae30a` | `9cad0d3` (with its report) | [2026-10-23-delete-entry](reports/2026-10-23-delete-entry.md) |
| O51, logging several folders with one set-up (D90) | Done, not merged | `log-several-folders`, from `delete-entry` at `9cad0d3` | One commit with its report | [2026-10-23-log-several-folders](reports/2026-10-23-log-several-folders.md) |

The four branches of 1.1.1, from `review-1.1.0` to `release-1.1.1`, were merged into
`main` as fast-forwards on 2026-10-22. With the user's approval they were deleted with
`git branch -d`, at `2a95784`, `790177d`, `3cedd34` and `3108c63`. None had been
pushed.

The branches above, from `o20-freeze-schema-v1` to `queue-check-state`, were merged
into `main` as one fast-forward on 2026-10-22; "Done, not merged" in the rows above
`queue-check-state` describes them before that merge. With the user's approval they
and `release-1.1.0` were deleted with `git branch -d` on 2026-10-22, at the commits in
the table. None had been pushed, so none existed on GitHub.

The milestone branches are deleted; `main` holds every commit of them. On 2026-10-12,
with the user's approval, `m8-release` was deleted on GitHub and these merged local
branches were deleted, at the commits shown: `m8-release` (`b5e6609`),
`docs-review-m5` (`43f4520`), `m3a-settings` (`f772059`), `m4-viewer` (`dd8d95d`),
`m5-transfer-core` (`ca5c145`), `m6-move-copy-tab` (`283d8a8`) and
`m7-packaging-migration` (`1f8001b`). After 1.0, each piece of work has its own branch,
deleted after its merge.

Commits between the milestones on `main`: `814417c` (decisions D1–D3 in the spec),
`89e94ac` (the user's PowerShell deny rule in `.claude/settings.json`), `6028895` and
`68fb49c` (D29, D30), `257244c` (documentation review), `77ed32c` (the user's
narrower UNC pattern in the safety hook), `a9079d5` (documents for the next agent
after Milestone 4) and the documentation review after Milestone 5 (branch
`docs-review-m5`).

## Open items

Requests, faults, questions and known gaps that are not yet decided or done. The
default is what an agent proposes unless the user decides otherwise. Raise each item
in the plan for its work. When it is decided, record it in `docs/DECISIONS.md`,
update `SPEC.md`, and move it to "Closed items" below. "M0 review <n>" refers to the
table in [reports/M0.md](reports/M0.md). The next free number is O52.

| ID | Item | When | Proposed default | Origin |
| --- | --- | --- | --- | --- |
| O19 | GUI for the confirmed "Upgrade database" action | With the first real schema migration | A button in the Settings tab's database section, shown only when the schema needs an upgrade, plus a startup message that points to it. Deferred by D30; until then an older database gives a red status line (D38). | D6; D29; D30 |
| O40 | Four suspicions from the release review, not confirmed: path work on the Qt main thread (the Log tab's folder field calls `WNetGetConnectionW` on each change; New database checks `exists()`); an `OSError` during Check before delete or Compare with laptop copy leaves the check row without `finished_at`; `legacy.main()` does not catch a `sqlite3.IntegrityError` other than a repeated location; a read-only connection cannot roll back a hot journal after a crash | When a fault points at one of them | Confirm each with a test before changing code. Details: the release review, "Unconfirmed suspicions". | Release review |
| O37 | Small files copy slowly to the NAS: about 18 to 25 ms per 64 KB file, with or without the flush, and more files at once help little. A day of 1 s files is about 26 minutes per channel. | Not needed for 1.x (D72) | Measure which per-file step costs most (create, write, flush, set the time, check the name, rename) before changing the copy engine. Measure the D75 identity check per file at the same time. | NAS field test, 2026-10-05 |

## Closed items

Decided items are in `docs/DECISIONS.md` (D1–D90). The M0 review table in
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
| O20 | Frozen copy of the version 1 schema | D77 (2026-10-20) |
| O42 | Code signing of the two programs | Closed by the user on 2026-10-20: "no issue" |
| O38 | Viewer filters on site, project and band take several choices | D78 (2026-10-20) |
| O43 | A new Log tab entry keeps the fields of the previous one | D79 (2026-10-20) |
| O44 | Import and export a Log tab template file | D80 (2026-10-20) |
| O45 | A queue in the Archive / copy tab | D81 (2026-10-20) |
| O41 | A batch Check archive for many recordings | D81 (2026-10-20): Check archive items in the queue |
| O46 | Fill Log tab fields from the recorder's log files | D82 (2026-10-21) |
| O47 | Copy and archive the recorder's log files with the recording | D83 (2026-10-21) |
| O48 | The Log tab's message line shows no state (user's manual test, 2026-10-22) | D84 (2026-10-22) |
| O49 | A queue archive whose check did not pass showed as Failed (user's manual test, 2026-10-22) | D85 (2026-10-22) |
| O22 | SQLite on SMB: scheduled backup of the catalogue outside the app | Closed by the user on 2026-10-22: a backup runs outside the app |
| O50 | The band filled in from fc | D88 (2026-10-23) |
| O39 | Deleting a catalogue entry that was added by mistake | D89 (2026-10-23) |
| O51 | Logging several recordings with one set-up | D90 (2026-10-23) |

## Pending checks for the user

Things that cannot be tested on the development PC, or were tested only partly.

- **The manual test of 1.2** (2026-10-23): `dev/test-1.2/CHECKLIST.html` with the
  build `dist/test-1.2`, on the data in `dev/test-1.2/data`. The page exports the
  results and comments as a text file to send back. The user ran it on 2026-10-23
  and sent the export: 30 of 33 steps passed and none failed, with no comments. Step
  3.1 (switching to Several folders) and step 3.11 (leaving the mode asks first)
  were not marked. Step 3.16 (Cancel during a long scan, optional) was not run: the
  test data scans too fast for it.

- **The cost on the NAS** of the D73 check on each connection and of the D75 identity
  check on each file. Neither was measured; locally neither is measurable. Measure
  with O37.
- **Check before delete through a Windows share of the same PC** refuses files whose
  size is not a multiple of 512 bytes, most likely, with WinError 87 (D85,
  2026-10-22). M8.md, part 2 recorded that every file failed; the manual test of
  2026-10-22 read 64,000-byte files and failed 4,000-byte files. A limit of such a
  share; the real NAS read 1,000,000-byte files.

On 2026-10-22 the user ran the manual test of 1.1.1 (`dev/test-1.1.1/CHECKLIST.html`,
build `dist/test-1.1.1`): every check passed. After it, the button under "Unfinished
transfers" was renamed Open in form (D86).

On 2026-10-22 the user reported that the field checks of version 1.1 passed with the
1.1.0 build: the queue against the real NAS with Pause and Start part-way through a
large archive (D81), several real folders in a row (D79), a template in a shared
folder (D80), the Viewer's tick-box filters (D78), each in dark mode, and a recorder
recording logged, archived with its log files, checked before delete and deleted from
the laptop (D82, D83).

On 2026-10-20 the user reported that the pilot passed. These two checks are closed
on that report:

- **D75 on the NAS:** an archive from a laptop passes as before, and so do its Check
  before delete and Delete laptop copy; an archive of a folder logged under one NAS
  name to the same folder under another name is refused at the preview.
- **D76 across two PCs:** an edit opened on one PC while another PC archives the same
  recording. The user answered "all passed" to a question that named this check. The
  agent asked the user to say so if it was not tested.

The Milestone 1 exe check (`dist/smoke-2/`) was confirmed by the user on 2026-10-02.
The Milestone 6 manual test on this PC passed on 2026-10-04. The release review ran on
2026-10-11 ([reports/2026-10-11-release-review.md](reports/2026-10-11-release-review.md)).
The checks of D73, D75 and D76 with `dist/m8-2` passed on this PC on 2026-10-12
([reports/M8.md](reports/M8.md), part 2).

## Files for the user to remove

Agents may not delete files. These are gitignored and safe to remove by hand. The
user removed `src/iqdm/transfer/scripts/`, an empty package left from before D48, on
2026-10-12; its removal was committed.

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
  `dist/m8-2`), and `dist/m8-2/`, `build/work-m8-2/` and `build/m8-2-build.log`
  (superseded by `dist/release-1.0.0`, which stays).
- After the release review (2026-10-11): `dist/review-1/`, `build/work-review-1/`,
  `build/review-1-build.log` and `dev/review/` (reproductions, screenshots and a
  scratch database). The pytest folders under `%TEMP%\pytest-of-Perry\` hold
  directory junctions from the review and from the D75 tests. Remove each as a link,
  so that its target is not touched.
- `dev/scratch.db`, made to check the README's run commands.
- `dev/o38-shots/` (Viewer filter screenshots, their script and two scratch
  databases, 2026-10-20).
- `dev/o43-shots/` (Log tab screenshots, their script, and synthetic recordings and
  scratch databases in its `run-*` folders, 2026-10-20).
- `dev/o44-shots/` (template dialog screenshots, their script and two scratch
  databases, 2026-10-20).
- `dev/o45-shots/` (queue screenshots, their script and scratch databases,
  2026-10-20).
- `dev/o46-shots/` (Log tab screenshots with a recorder log, their script and `run-*`
  folders, 2026-10-21).
- `build/work-release-1.1.0/` (PyInstaller's work folder of the 1.1.0 build).
- `build/work-release-1.1.1/` and `build/release-1.1.1-build.log` (the 1.1.1 build).
  `dist/release-1.1.1/` stays; `dist/release-1.1.0/` can go once the team runs 1.1.1.
- After the review of 1.1.0: `dist/review-1.1/`, `build/work-review-1.1/`,
  `build/review-1.1-build.log` and `dev/review-1.1/` (probe tests and reading
  scripts).
- After the manual test of 1.1.1: `dist/test-1.1.1/`, `build/work-test-1.1.1/` and
  `build/test-1.1.1-build.log` (built from `48804a2`; it still shows version 1.1.0),
  and `dev/test-1.1.1/` (the checklist `CHECKLIST.html`, its data script and 115.6 MB
  of synthetic data with a scratch database).
- `dev/o50-probe/` (a script that checks the italic band box offscreen, 2026-10-23).
- After the manual test of 1.2: `dist/test-1.2/`, `build/work-test-1.2/` and
  `build/test-1.2-build.log` (built from `ca79895`; it still shows version 1.1.1), and
  `dev/test-1.2/` (the checklist `CHECKLIST.html`, its harness copy
  `page-check.html`, `make_test_data.py`, `check_expectations.py`, and 11 MB of
  synthetic data with a scratch database in `data`).
- `dev/o51-probe/` (timing, size-check and screenshot scripts, 2026-10-23). Their data
  is in the session's scratch folder under `%TEMP%\claude\`: about 720,000 small
  synthetic files in `o51-size`.
- `dev/kickoff-head.txt` (the old `KICKOFF.md`, used to check its archive copy).
  `dist/release-1.1.0/` stays; `dist/release-1.0.0/` can go once the team runs 1.1.0.
- `recorder/` at the repository root: the user's two example recordings of
  2026-10-12. Cleaned copies of their logs are in `tests/data/recorder/`. The folder
  is not tracked; keep or remove it as you wish.
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
- **Git:** one branch per piece of work (one per milestone until 1.0). Stage files by
  explicit path; never `git add -A`. Merging, tagging, pushing and any git command
  other than `status`, `diff`, `log`, `add` and `commit` need the user's approval.
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
- **A test that leaves a question behind hangs the suite.** pytest-qt closes each
  window at teardown, after `monkeypatch` is undone. A main window whose Archive /
  copy queue still holds a waiting item then opens a real modal question, and the
  run never ends. Tests empty the queue before they end (`test_app_smoke.py`, D81).
  Run long suites with `timeout` in front, so a hang ends.
- **Code that deletes or overwrites a file** is listed in the Milestone 6 report
  (earlier: Milestone 5), section "Code paths that delete or overwrite a file", with
  the changes in the Milestone 7 report ("Code that creates or overwrites a file")
  and the Milestone 8 report, part 2. A change to such code lists its own changes in
  its report, as the milestone prompts asked for Milestones 5 and 6
  (`docs/KICKOFF_ARCHIVE.md`). The reports of 1.1 and 1.1.1 list their changes the
  same way.
- **A manual-test checklist** for the user is an HTML page under `dev/`, with small
  synthetic data made by a script next to it: `dev/test-1.1.1/` (the user may have
  removed it) held `CHECKLIST.html`, `make_test_data.py` and `check_expectations.py`.
  The script refuses an existing output folder. The app runs on the data with
  `IQDataManager.exe --config <data>\config.toml`, which names a scratch database
  made from `schema.sql`. Data files of 64,000 bytes (int16, 16 kHz, 1 s) and recorder
  logs padded to a multiple of 512 bytes let Check before delete pass through a
  Windows share of the PC (D85). `copy_workers = 1` slows a copy enough to pause it.
  Read the expected texts from the app offscreen before writing them into the page.
- **A message box with custom buttons** (such as the template pop-up of D87) is a
  module-level function, `log_tab.ask_template_conflicts()`. Tests replace that
  function with `monkeypatch`; `QMessageBox.question` stubs do not reach it.
- **A test module must not import a class named `Test...`.** Pytest tries to collect
  it, and a dataclass then raises a collection warning, which the configuration
  turns into an error. Tool classes are named accordingly (`SetSizes` in
  `tools/make_nas_testset.py`).
- **Reports:** every milestone, and after 1.0 every piece of work, ends with a report
  in `docs/reports/` that follows `docs/REPORT_TEMPLATE.md`, and an update to this
  file. After 1.0 the name is `<YYYY-MM-DD>-<topic>.md`.
- **`ruff format` only on the files you change.** Several files on `main` are not in
  `ruff format` style, and the project checks only `ruff check`. Running the formatter
  on a whole folder rewrapped unrelated code three times in Milestone 3.
- **A Windows share of a local folder** can stand in for the NAS in a manual test,
  because NAS locations must be UNC paths. Check before delete through such a share
  fails with WinError 87 for files whose size is not a multiple of 512 bytes, most
  likely; 64,000-byte files read (2026-10-22, D85; M8.md part 2 thought every file
  failed). Synthetic files of 4,000 bytes therefore fail there. Test the delete on the
  real NAS.
- **Screenshots of the GUI** render offscreen with the light palette. Set
  `QT_QPA_FONTDIR=C:/Windows/Fonts` for readable text. The user runs Windows in dark
  mode, so render with a dark palette too: set the `Base`, `Text`, `Window`,
  `WindowText`, `Button`, `ButtonText` and `PlaceholderText` roles, call
  `app.setPalette()` before the widget is built, and save `widget.grab()`. The
  offscreen style draws disabled buttons nearly like enabled ones; check button states
  in tests.
