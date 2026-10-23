# The Archive / copy tab in three pages (O58)

| | |
| --- | --- |
| Branch | `transfer-pages`, from `main` at `0a5b3cd` |
| Commits | The commit of this work and report |
| Tests | 1,975 passed, 4 skipped (`pytest`); `ruff check` clean |
| Report date | 2026-10-23 |
| Merge status | Not merged. The first of three branches of version 1.3.0. |

## Objectives against what was delivered

O58 in STATUS.md: "The Archive / copy tab shows the controls for copies, archives and
checks at once." The proposed default: "Pages Archive, Check and Copy under a shared
recording row, with the preview at the right and the queue and unfinished transfers in
two tabs below." The user approved the plan on 2026-10-23, with the recommended answers
to its questions 1 to 3.

| Objective | Status | Notes |
| --- | --- | --- |
| Pages Archive, Check and Copy under the recording row; the page sets the operation | Done | [transfer_tab.py](../../src/iqdm/gui/transfer_tab.py) `_build_pages()`, `page()`, `show_page()`, `operation()`. `test_the_page_sets_the_operation_and_drops_the_other_preview`, `test_loading_a_local_recording_prepares_an_archive`. |
| The Archive page's destination is the NAS folder for archives plus the relative path | Done | `_fill_archive_destination()`, [movecopy.py](../../src/iqdm/movecopy.py) `archive_destination()`. `test_the_nas_folder_fills_in_the_archive_destination`, `test_the_archive_destination_keeps_the_relative_path`. |
| The Copy page holds the scope, the channels, the timeline and "Folder for copies", which starts from Settings | Done | `_build_copy_page()`, `apply_config()`. `test_viewer_copies_go_to_the_copy_pages_folder`, `test_a_new_copy_folder_in_settings_reaches_the_copy_page`. |
| The Check page holds Check archive and Compare with laptop copy | Done | `_build_check_page()`, `_show_check()`. `test_the_check_page_runs_no_transfer`, `test_compare_with_laptop_copy_clears_the_mark` (which also checks that the Check page's Compare choice counts while another page is shown). |
| The preview at the right; the queue and the unfinished transfers in two tabs below | Done | `_build()`: a splitter, and `lists` with the counts in the tab names. |
| The pages are locked while an operation runs | Done | `_update_buttons()`. `test_the_pages_are_locked_while_an_operation_runs`. |
| Question 1: Check before delete and Delete laptop copy on the Archive page | Done | `_build_laptop()`. `test_archive_check_and_delete` checks that both buttons are on the Archive page, then runs the check and the delete with No and Yes as before. |
| Question 2: the page the Viewer's button opens | Done | `movecopy.page_for()`; `load_recording(choose_page=True)` from `MainWindow.open_transfer()`. `test_a_laptop_recording_opens_on_the_archive_page`, `test_an_archived_recording_opens_on_the_page_its_laptop_copy_needs` (five cases), `test_load_keeps_the_page_and_the_viewer_button_chooses_it`, `test_archive_copy_opens_the_recording_in_its_tab`. |
| Question 3: the tab's name stays "Archive / copy" | Done | No change. |
| Visible text in `tests/test_user_text.py` | Done | `test_transfer_tab_text_is_plain` now visits every page, for a laptop recording and for an archived one that is not verified. |

## Decisions made

D96, "The Archive / copy tab in three pages".

## Changes from the plan

- **Viewer copies use the Copy page's folder in this branch.** The plan put that in
  the third branch. It moved here because the Copy page's folder field exists from
  this branch on, and a Viewer copy that ignored it would confuse. `item_for_recording()`
  takes `copy_folder` in place of `config`. Its refusal now reads "…no folder for
  copies is chosen. Choose it on the Copy page first." The refusal for archives reads
  "Choose the NAS folder for archives on the Archive page first." The third branch
  replaces both refusals.
- **Each page has its own Compare dropdown.** The plan named one for the Check page;
  the Archive and Copy pages needed their own too, because a copy may use "Sizes only"
  and an archive's choice also sets Check before delete.
- **`dest_edit` and `hash_combo` became properties** that return the field of the page
  shown. This keeps the tests and the code that reads "the destination" short.
- **Two faults found in the screenshots** were fixed: a new tab showed an empty
  progress bar and an empty preview list until the first operation (D96, last point).
  `test_a_new_tab_shows_no_progress_and_asks_for_a_preview`.
- **A text for an archived recording without an app archive.** The old tab showed
  "Load a recording." in the laptop-copy group for a recording logged on the NAS that
  was already compared. The Archive page now says "The app did not archive this
  recording to its NAS folder, so it has no laptop copy to check or delete here."

## Code paths that delete or overwrite a file, or delete catalogue rows

| Path | Change |
| --- | --- |
| `transfer/delete.py`, `operations.delete_laptop_copy()` | None |
| `TransferTab.start_delete()` | The Delete laptop copy button moved to the Archive page. The method, its gate (`LaptopCopy.can_delete`), its question (default No) and its call are unchanged. `test_archive_check_and_delete` checks the button's page, that No deletes nothing and that Yes deletes the 11 files. |
| `TransferTab.start_check_before_delete()` | Reads the Archive page's Compare dropdown. It still refuses "Sizes only" (`test_check_before_delete_needs_a_hash_mode_that_reads_content`). |
| Copy engine, verification, renames | None |
| Catalogue rows | None deleted |

## Not done in this piece of work

| Item | Where it lands |
| --- | --- |
| The check after each archive, and the check-after box removed (O57) | Branch `check-after-archive`, D97 |
| Items from the Viewer that wait for a folder (O59) | Branch `queue-asks-for-folder`, D98 |
| USER_GUIDE.md section 5 | Rewritten in the last branch of 1.3.0, for the screen as it ends |

## Untested or not testable here

- The layout by eye on a real display, in light and dark mode, and the splitter by
  hand. Offscreen screenshots with both palettes were checked
  (`dev/o58-shots/shots.py`); the user checks the real display in the manual test of
  1.3.0.

## Issues found in self-review

1. **The NAS folder field stays usable during an operation.** This was so before (the
   field was missing from the list of widgets that `_update_buttons()` disables). The
   branch keeps it on purpose, for recordings added from the Viewer during a queue
   run. `_nas_folder_changed()` leaves the form's destination alone while an
   operation runs, so a running transfer's form is not changed.
2. **Format.** `ruff format --check` would rewrap some lines in `transfer_tab.py` and
   `app.py`, among them lines this branch did not touch. The project checks
   `ruff check` only; the files were left as they are.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 1,975 passed, 4 skipped; clean |
| The manual test of 1.3.0 | User | The pages on a real display, after all three branches |

## Build output and files for the user to remove

`dev/o58-shots/` (the screenshot script and the folder `run1` with its data and
screenshots), listed in STATUS.md.

## Recommendation and question

Continue with O57 on `check-after-archive`, from this branch.
