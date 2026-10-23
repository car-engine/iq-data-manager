# Logged by is typed by the user (O53)

| | |
| --- | --- |
| Branch | `logged-by-typed`, from `batch-log-rf-rows` at `b5aaa55` |
| Commits | The commit of the code and this report |
| Tests | 1,943 passed, 4 skipped (`pytest`, 136.95 s); `ruff check` clean |
| Report date | 2026-10-23 |
| Merge status | Not merged |

The third piece of work for version 1.2.1. Team feedback on 1.2: "Logged by" was
filled in with the Windows login, which on a shared laptop names the laptop's account.
The user approved the plan on 2026-10-23, chose that Clear form empties the field, and
chose to keep the Windows login for transfers, checks and deletes.

## Objectives against what was delivered

O53's proposed default: "The field starts empty, with the placeholder 'Your name',
and Clear form empties it. A typed name stays across folders, saves and mode
switches. Transfers, checks and deletes keep the Windows login as 'By'."

| Point | Status | Notes |
| --- | --- | --- |
| Empty at the start, with the placeholder | Done | `LogTab.clear_form()` in [log_tab.py](../../src/iqdm/gui/log_tab.py) empties the field; `LOGGED_BY_PLACEHOLDER`. The existing to-do item blocks the save. Tests: `test_logged_by_starts_empty_for_the_user_to_type`, `test_scan_fills_in_fs_and_leaves_fc_and_site_to_do`, `test_folders_are_added_scanned_and_sorted_by_start` (the to-do item for all folders). |
| Clear form empties it | Done | `test_clear_form_resets_every_field`. |
| Stays across folders, saves and mode switches | Done | Nothing else resets the field. Tests: `test_a_typed_name_stays_for_the_next_folder_and_after_a_save`, `test_a_typed_name_stays_across_the_mode_switch`. |
| Transfers, checks and deletes keep the login | Done, unchanged | `entry.default_logged_by()` stays for `TransferTab(performed_by=...)` and the delete record. |

The placeholder is checked in `test_log_tab_text_is_plain`.

## Decisions made

- D94. Logged by is typed by the user.

## Changes from the plan

None.

## Code paths that delete or overwrite a file, or delete catalogue rows

None. The value written to `recordings.logged_by`, and for a folder logged in place on
the NAS to its check row's `performed_by` (D2), is now the typed name.

## Untested or not testable here

- Entries logged before 1.2.1 keep their stored names; nothing changes them.

## Issues found in self-review

1. **The checklist's wording stays "Enter the logged-by name".** It names the field
   as before. O54 marks the field itself.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| The manual test of 1.2.1: the field is empty at the start and after Clear form, and the name stays for the next folder | User | The screen by eye |

## Build output and files for the user to remove

None.

## Recommendation and question

Continue with O54 (required fields marked on the field) on a branch from this one.
