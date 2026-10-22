# Deleting an entry added by mistake (O39)

| | |
| --- | --- |
| Branch | `delete-entry`, from `band-from-fc` at `12ae30a` |
| Commits | The commit of the code and this report |
| Tests | 1,868 passed, 4 skipped (`pytest`, 133.53 s); `ruff check` clean |
| Report date | 2026-10-23 |
| Merge status | Not merged |

The second piece of work for version 1.2, as in the plan the user approved on
2026-10-23. The user chose the Log tab's edit mode for the action and a JSON copy of
the entry on the PC that deletes it. The branch starts from `band-from-fc`, because
both change [log_tab.py](../../src/iqdm/gui/log_tab.py); each merges as a
fast-forward.

## Objectives against what was delivered

The prompt "Version 1.2" asked the plan to settle these points: "which entries may be
deleted (none with an archive, copy or delete row?); where the action sits; the
confirmation; whether a trace of the deletion is kept anywhere; two PCs at once; that
files are never touched."

| Point | Status | Notes |
| --- | --- | --- |
| Which entries | Done | Only check rows without a parent may be in the history: the row of D2, Check archive, Compare with laptop copy. `repository.blocks_deletion()` ([repository.py](../../src/iqdm/db/repository.py)); `delete_recording()` deletes those rows first and refuses any other. Tests: `test_blocks_deletion`, `test_delete_takes_the_check_rows_without_a_parent`, `test_an_archive_or_a_copy_row_keeps_the_recording`, `test_an_archive_or_a_copy_keeps_the_entry`, `test_an_archived_or_copied_entry_is_not_deleted`. |
| Where the action sits | Done | "Delete entry..." in the Log tab, in edit mode only. `test_the_delete_button_shows_in_edit_mode_only`. Also refused while this PC's queue holds the recording or the Archive / copy tab works on it: `TransferTab.deletion_blocked()`; tests `test_the_queue_holds_a_recording_against_a_delete`, `test_an_operation_on_the_recording_holds_it_against_a_delete`, `test_a_recording_another_tab_holds_is_not_deleted`. |
| The confirmation | Done | `confirm_delete()` with "Delete entry" and Cancel (the default). `entry.delete_question()` names the recording, folder, start, channels, files, check rows, that the files stay, and where the copy goes. Tests: `test_the_question_names_the_folder_start_and_files`, `test_cancel_deletes_nothing`. |
| A trace | Done | `deletion_record.write_record()` ([deletion_record.py](../../src/iqdm/deletion_record.py)) writes `deleted-entries/recording-<id>-<time>.json` next to the settings file before the delete, create-only. Tests: the content in `test_an_entry_without_history_is_deleted_and_its_files_stay`, `test_an_existing_record_is_kept_and_nothing_is_deleted`. The architecture tests now check the module for replacing, moving and subprocess calls. |
| Two PCs | Done | The check runs before the question and again inside the delete's transaction (`entry.check_deletion()`, `entry.delete_entry()`). A transfer whose recording was deleted meanwhile stops at its first row: `insert_transfer()` raises `NotFoundError` with a plain message. Tests: `test_a_change_after_the_question_deletes_nothing`, `test_an_entry_deleted_on_another_pc`, `test_a_save_over_a_deleted_entry_says_so`, `test_a_save_over_an_entry_deleted_elsewhere`, `test_a_transfer_of_a_deleted_recording_is_not_found`, `test_a_copy_of_a_recording_deleted_after_the_preview_copies_nothing`. |
| Files never touched | Done | No file function in the delete path except the new copy. Two tests compare every file of the recording folder (name, size, and in `test_delete_entry.py` the modification time) before and after a delete. |

After a delete, the form is cleared, the Viewer refreshes and the Archive / copy tab
drops the recording from its form
(`test_a_log_tab_delete_refreshes_the_viewer_and_the_archive_copy_form`).
`tests/test_user_text.py` checks the new texts (`test_delete_text_is_plain`).

## Decisions made

- D89. Deleting an entry added by mistake. Replaces D41.

## Catalogue rows deleted

| Code | Rows | Rule |
| --- | --- | --- |
| `repository.delete_recording()` | The `recordings` row; its `channels` and `recording_params` rows by cascade; its `transfer_log` rows with `operation = 'check'` and no `parent_id` (new) | Refused with `HasTransferHistoryError` while any other row exists. Its only caller in the app is `entry.delete_entry()`, inside one write transaction that first compares the entry and its rows with those read before the question. |

## Code that creates or overwrites a file

| Code | What it writes | Rule |
| --- | --- | --- |
| `deletion_record.write_record()` | `deleted-entries/recording-<id>-<time>.json` next to the settings file | New file only (`open("xb")`), flushed with `os.fsync`. An existing file is refused and kept. |

No code path that copies, renames or deletes a recording's file changed.
`insert_transfer()` now raises `NotFoundError` for a recording that is gone; before,
SQLite's foreign-key error reached the caller. In both cases the transfer stops
before its first file.

## Changes from the plan

- A blocked delete gives its reason on the message line after a short check in a
  worker ("Checking the entry..."). The plan described the same check. The button is
  enabled in edit mode and does not show whether the entry can be deleted, because
  that needs a database read.
- The plan said a transfer of a deleted recording raises `TransferError`. It raises
  `NotFoundError`, a database error the tabs already show, with the message
  "Recording 12 is no longer in the catalogue. It may have been deleted on another
  PC."
- The two refusals of the Archive / copy tab are functions, `queue_holds_text()` and
  `tab_holds_text()`, so the text test can check them.

## Untested or not testable here

- Two real PCs on the NAS: a delete on one while the other archives or saves an
  edit. The tests run both sides against one database under `tmp_path`.
- The question and the messages by eye, in light and dark mode. The user checks
  these in the manual test of 1.2.
- A delete when the settings folder cannot be written (for example a full disk). The
  code refuses before the delete; no test makes the folder unwritable.

## Issues found in self-review

1. **Unsaved edits in the form go with the delete.** A user who changes fields in
   edit mode and then deletes loses those changes without a question; the question
   names only the stored entry. Left unchanged: the entry is deleted either way.
2. **The copy is not removed when the delete fails.** If the transaction fails after
   the copy was written, the copy stays, and the message says so. No module other
   than `transfer/delete.py` deletes files, so the app does not remove it.
3. **A queue item that is finished does not hold the recording.** A finished copy
   leaves a `copy` row, which refuses the delete anyway. A finished Check archive
   leaves a check row without a parent, which goes with the entry.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| Manual test of 1.2: delete a local entry and one logged in place; try an archived one; cancel; check the copy and that the folder is unchanged | User | The screen and the record file by eye, before the release |
| A delete on one PC while another PC has the entry open in edit mode, on the real catalogue | User | Two PCs and real SMB locking |

## Build output and files for the user to remove

None.

## Recommendation and question

Review the O51 plan next; the user asked to discuss it again before any code. Merge
`band-from-fc` and `delete-entry` after the manual test of 1.2.
