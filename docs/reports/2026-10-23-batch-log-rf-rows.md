# "Several folders" shows each folder's log rows (O55)

| | |
| --- | --- |
| Branch | `batch-log-rf-rows`, from `wheel-guard` at `e9977e6` |
| Commits | The commit of the code and this report |
| Tests | 1,941 passed, 4 skipped (`pytest`, 134.17 s); `ruff check` clean |
| Report date | 2026-10-23 |
| Merge status | Not merged |

The second piece of work for version 1.2.1. Team feedback on 1.2: after several
folders were scanned, the side panel said that the USRP, the USRP gain and the Clock
reference were filled in from the recorder's log, but the RF chain section did not
show them. The saved entries held them. The user approved the plan on 2026-10-23 and
chose read-only rows.

## Objectives against what was delivered

O55's proposed default: "A read-only list under section 5 shows the selected folder's
log rows, the shared rows they replace, and the log's sample type."

| Point | Status | Notes |
| --- | --- | --- |
| The selected folder's log rows | Done | `batchlog.log_shown()` in [batchlog.py](../../src/iqdm/batchlog.py) gives the rows `form_for()` saves. A read-only table under section 5 in [log_tab.py](../../src/iqdm/gui/log_tab.py) lists them in italics, with a tooltip on how to change one. Tests: `test_the_log_rows_shown_are_the_ones_saved`, `test_the_selected_folders_log_rows_are_shown` (also after a change of the selected folder), `test_the_log_rows_shown_are_saved` (against the saved entry). |
| The shared rows they replace | Done | The line under the table, `log_rows_note()`. Tests: `test_a_shared_row_that_the_log_replaces_is_named`, and `test_a_shared_usrp_row_stays_and_is_not_shown_as_replaced` for a typed USRP row, which the log leaves (D82). |
| The log's sample type | Done | Named in the same line when it differs from section 3's. `test_the_logs_sample_type_is_named_when_it_differs`. |
| Hidden where it does not apply | Done | No log, or "One folder" mode. `test_no_log_rows_without_a_log`, `test_a_folder_without_a_log_shows_no_log_rows`, `test_the_log_rows_go_with_one_folder_mode`. |

The new texts are in `test_several_folders_text_is_plain` in
`tests/test_user_text.py`.

Offscreen renders of section 5 in the light and the dark palette, from
`dev/o55-shots/shots.py`, showed the table at the height of its rows and readable in
both.

## Decisions made

- D93. "Several folders" shows each folder's log rows. Amends D90.

## Changes from the plan

None.

## Code paths that delete or overwrite a file, or delete catalogue rows

None. The change adds a view of values that were saved already.

## Untested or not testable here

- The screen by eye on the user's PC; the offscreen renders were checked.
- Real recorder logs of several folders on the NAS. The tests use logs in the format
  of the examples in `tests/data/recorder`.

## Issues found in self-review

1. **The rows cannot be changed per folder.** As planned: the user unticks the folder
   and logs it in "One folder" mode. D93 says what per-folder rows would need.
2. **`log_tab.py` is not in `ruff format` style**, as before this change. Only the
   new lines follow it.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| The manual test of 1.2.1: several folders with logs, one without, a shared USRP gain row; select each folder and compare section 5 with the saved entries in the Viewer | User | The screen by eye |

## Build output and files for the user to remove

- `dev/o55-shots/` (the screenshot script). The renders are in the session's scratch
  folder under `%TEMP%\claude\` (`o55-light`, `o55-dark`, `o55-light-2`,
  `o55-dark-2`).

## Recommendation and question

Continue with O53 (Logged by typed by the user) on a branch from this one.
