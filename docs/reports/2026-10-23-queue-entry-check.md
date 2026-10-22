# A deleted entry's number given again (O52)

| | |
| --- | --- |
| Branch | `queue-entry-check`, from `log-several-folders` at `f7ab319` |
| Commits | The commit of the code and this report |
| Tests | 1,925 passed, 4 skipped (`pytest`, 132.04 s); `ruff check` clean |
| Report date | 2026-10-23 |
| Merge status | Not merged |

Found while preparing the manual test of 1.2. Step 2.4 deletes recording 5, the
newest entry, and step 3.10 then saves recordings 5 to 8: the next new entry got the
deleted entry's number. The user's manual test showed the same numbers. The user
approved the proposed default on 2026-10-23, for version 1.2.0.

## Objectives against what was delivered

O52's proposed default: "Keep the numbering for 1.2: say so in the user guide and D89.
A queue item and a transfer check before they start that the entry is the one they
were made for (its creation time), and refuse otherwise. `AUTOINCREMENT` waits for the
first schema change."

| Point | Status | Notes |
| --- | --- | --- |
| Keep the numbering, and say so | Done | D91, a note on D89, SPEC sections 6 and 8, the user guide (the delete paragraph). |
| A queue item checks its entry | Done | `QueueItem.created_at`, set where items are made from the Viewer (`item_for_recording()`) and from the form (`TransferTab.add_current_to_queue()`, from the preview). `transferqueue.entry_problem()` runs first in `run_item()`: another entry under the number, or none, gives "Not started" with the reason. Tests: `test_an_item_does_not_run_for_an_entry_that_took_its_number`, `test_a_check_archive_item_is_checked_the_same_way`, `test_an_item_for_a_deleted_entry_is_not_started`, `test_an_item_for_its_own_entry_runs`, the `created_at` assertions in `test_a_laptop_recording_is_archived_into_the_nas_folder` and `test_add_to_queue_from_the_form`. |
| A transfer checks its preview's entry | Done | `run_transfer()` compares `repository.created_at()` with the preview's entry in the transaction that writes the first row, and raises `TransferError` before any file is copied. `test_a_preview_does_not_run_for_an_entry_that_took_its_number`. |
| `AUTOINCREMENT` | Deferred | To the first schema migration (HANDOFF.md, section 5). |

The two new texts are in `test_delete_text_is_plain` in `tests/test_user_text.py`.

## Decisions made

- D91. A deleted entry's number can be given again. Amends D89.

## Changes from the plan

None.

## Code paths that delete or overwrite a file, or delete catalogue rows

None changed. The check adds a refusal before a transfer's first row and before a
queue item runs.

## Untested or not testable here

- The case itself across two PCs: a delete and a new entry on one, a queued item on
  the other. The tests make the second entry on the same database and set its
  creation time a second later.
- An entry deleted and replaced within the same second has the same `created_at` and
  is not told apart. D91 states this limit.

## Issues found in self-review

None.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| None beyond the tests | | The change adds a refusal that the screen shows as an existing queue state, "Not started", with its note. |

## Build output and files for the user to remove

None.

## Recommendation and question

Merge with the three branches of 1.2 into `main`, then release 1.2.0.
