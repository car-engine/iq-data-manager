# Queue items from the Viewer wait for their folder (O59)

| | |
| --- | --- |
| Branch | `queue-asks-for-folder`, from `check-after-archive` at `db22f57` |
| Commits | The commit of this work and report |
| Tests | 1,996 passed, 4 skipped (`pytest`); `ruff check` clean |
| Report date | 2026-10-23 |
| Merge status | Not merged. The last of three branches of version 1.3.0; it holds all of it. |

## Objectives against what was delivered

O59 in STATUS.md: "Adding recordings from the Viewer to the queue without a NAS folder
for archives, or without a default copy folder, is refused; the user must choose the
folder and add them again." The proposed default: "The items join the queue and wait
for the folder; the tab opens the page with the missing field. Start stays disabled
while an item waits." The user approved the plan on 2026-10-23, with the recommended
answers to its questions 5 to 7.

| Objective | Status | Notes |
| --- | --- | --- |
| The items join the queue and wait for the folder | Done | [transferqueue.py](../../src/iqdm/transferqueue.py) `item_for_recording()`, `QueueState.NEEDS_NAS_FOLDER` and `NEEDS_COPY_FOLDER`, `QueueItem.rel_path`. `test_a_laptop_recording_is_archived_into_the_nas_folder`, `test_an_archived_recording_is_copied_to_the_copy_folder`, `test_items_that_wait_for_a_folder_do_not_run`. |
| The tab opens the page with the missing field, and marks it | Done | [transfer_tab.py](../../src/iqdm/gui/transfer_tab.py) `_ask_for_folder()`, `_show_folder_marks()` (the Log tab's `mark_style()`, D95). `test_viewer_archives_wait_for_the_nas_folder`, `test_viewer_copies_wait_for_the_copy_folder`, `test_viewer_recordings_go_to_the_queue` (the main window). |
| Choosing the folder fills in each waiting item's destination and previews it | Done | `TransferQueue.fill_folder()`, `TransferTab._fill_waiting()`. `test_a_chosen_folder_gives_the_waiting_items_their_destination`, `test_a_filled_destination_that_repeats_an_item_is_not_started`, and the tab tests above. |
| Start stays disabled while an item waits (question 6) | Done, with a change | `_update_buttons()`, `_folder_missing()`, `start_queue()`. Start stays disabled while a folder that items wait for is empty; once the field holds text, Start fills the items in and runs (self-review, issue 1). `test_viewer_archives_wait_for_the_nas_folder`, `test_start_takes_a_folder_typed_without_enter`. |
| `run_item()` refuses an item without a destination before its preview | Done | `test_an_item_without_a_destination_is_not_started`. |
| The copy folder is the Copy page's (question 7) | Done | From the first branch (D96). |
| Items added during a queue run | Done | Both folder fields stay usable. `test_items_added_while_the_queue_runs_get_their_folder_meanwhile`, `test_the_pages_are_locked_while_an_operation_runs`. |
| USER_GUIDE.md section 5 for the new screen | Done | Rewritten for the pages (D96), the check after each archive (D97) and the waiting items (D98). Section 4 says which page the Viewer's button opens. |
| Visible text | Done | `test_queue_text_is_plain`: the waiting texts, the required placeholder and the summary words. |

## Decisions made

D98, "Queue items from the Viewer wait for their folder". It amends D81.

## Changes from the plan

- **Two copies of one recording that both wait for the copy folder repeat each
  other.** The plan did not name this case. The folder would give both the same
  destination, so the second is refused when it is added
  (`test_items_that_wait_for_a_folder_do_not_run`).
- **The folder fills the items on Enter, on leaving the field, and on Browse.** A fill
  on each typed character would have given the items a part of the path.
- **A waiting item holds its recording against a form archive** (D86), with its own
  line under the buttons. `test_a_waiting_items_recording_is_not_archived_from_the_form`.
- **The end-of-queue summary** names its parts from a table (`SUMMARY_WORDS`), because
  "needs a NAS folder" in lower case would have lost the capitals of NAS.

## Code paths that delete or overwrite a file, or delete catalogue rows

None changed. The branch changes when a queue item gets its destination and when Start
may run. The copy engine, the checks and the delete module are unchanged. `run_item()`
gains a refusal before any file is read.

The whole version, for the table "Code paths that delete or overwrite a file"
(HANDOFF.md, section 3):

| Path | Version 1.3.0 |
| --- | --- |
| `transfer/delete.py`, `operations.delete_laptop_copy()` | Unchanged |
| `TransferTab.start_delete()` | Moved with its button to the Archive page; gate, question and call unchanged (D96) |
| `operations.check_before_delete()` | Unchanged; it now runs after every passed archive, from the form and the queue (D97) |
| `copier.py`, `verify.py`, `operations.run_transfer()` | Unchanged |
| Catalogue rows | None deleted; each archive adds one `check` row (D97) |

## Not done in this piece of work

| Item | Where it lands |
| --- | --- |
| A merge, a version number, release notes and a build | Version 1.3.0's release, with the user's approval, after the manual test |

## Untested or not testable here

- The frame, the line under the queue and the page switch on a real display, in light
  and dark mode. Offscreen screenshots of both palettes were checked
  (`dev/o58-shots/run2`); the manual test of 1.3.0 covers the real display.
- Focus: the tests check the page and the field's mark. The cursor in the field needs
  a real display.

## Issues found in self-review

1. **A folder typed without Enter.** The first version kept Start disabled until every
   item had its folder, and filled the items only on Enter, on leaving the field, or
   on Browse. A disabled button takes no click and no focus, so a user who typed the
   folder and clicked Start would have seen nothing happen. Fixed: Start is enabled
   once each folder that items wait for holds text, and Start fills the items in
   before it runs. `test_start_takes_a_folder_typed_without_enter`.
2. **The NAS folder field cleared by the program** (not by typing) leaves the form's
   archive destination as it was. Typing in the field, or Browse, refills it. This
   matters only to scripts, such as the screenshot script.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 1,996 passed, 4 skipped; clean |
| The manual test of 1.3.0 (`dev/test-1.3.0/CHECKLIST.html`) | User | The three branches on a real display, with synthetic data |

## Build output and files for the user to remove

`dev/o58-shots/run2` (screenshots and their data) and `dev/test-1.3.0/` after the
manual test, listed in STATUS.md.

## Recommendation and question

Run the manual test of 1.3.0. If it passes, merge `queue-asks-for-folder` into `main`
as a fast-forward (it holds all three branches) and release 1.3.0?
