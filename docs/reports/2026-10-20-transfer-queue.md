# A queue in the Archive / copy tab (open items O45 and O41)

| | |
| --- | --- |
| Branch | `transfer-queue`, from `log-templates` at `740fd54` |
| Commits | The commit of this work and report |
| Tests | 1,709 passed, 4 skipped (`pytest`), `ruff check` clean |
| Report date | 2026-10-20 |
| Merge status | Not merged. Merge after `log-templates`, as fast-forwards in order. |

## Objectives against what was delivered

O45 in `docs/STATUS.md` read: "A queue in the Archive / copy tab: add several archives
and copies, then Start; Pause pauses the whole queue". Its proposed default, approved
with the plan on 2026-10-20, was: "Items come from a Viewer multi-selection or from the
tab's form. Each item holds its own operation, destination, channels, range and check
mode, and Edit takes it back into the form. Each item is previewed again just before
it runs. Pause stops the running item safely, and Start resumes it, skipping the files
already copied. Optional Check before delete after each archive. Check archive items
close O41. The queue lives in memory."

| Objective | Status | Notes |
| --- | --- | --- |
| Items from a Viewer multi-selection | Done | [viewer_tab.py](../../src/iqdm/gui/viewer_tab.py): `ExtendedSelection`, `selected_ids()`, the "Add to queue" button with "Archive or copy" and "Check archive". [transferqueue.py](../../src/iqdm/transferqueue.py) `item_for_recording()` sets the destination. `test_several_recordings_go_to_the_queue`, `test_start_runs_the_items_in_turn`, `test_viewer_recordings_go_to_the_queue`. |
| Items from the tab's form | Done | "Add to queue" next to Run, after a passed preview. `test_add_to_queue_from_the_form`. |
| Each item holds its own settings; Edit takes it back into the form | Done | `QueueItem.request`; `edit_queue_item()` and `_fill_form_from_request()`; the item goes back in its place. `test_edit_puts_the_item_back_in_its_place`. |
| Previewed again just before it runs | Done | `run_item()` calls `preview_transfer()` first; errors give "Not started" and the queue goes on. `test_a_failed_preview_is_not_started`, `test_a_failed_item_does_not_stop_the_queue`. |
| Pause stops the running item safely; Start resumes it, skipping copied files | Done | `pause_queue()` asks first and cancels the task; the row is finished as `skipped`; the next run skips the files in place. `test_a_pause_stops_the_item_and_start_continues_it` (real files), `test_pause_then_start_finishes_the_item` (the tab). |
| Optional Check before delete after each archive | Done | "After each archive, run Check before delete", ticked by default; skipped with "Sizes only", with the reason. `test_an_archive_with_its_check_before_delete`, `test_sizes_only_skips_the_check_and_says_why`. |
| Check archive items close O41 | Done | `test_a_copy_and_a_check_archive`, `test_check_archive_items`. |
| The queue lives in memory | Done | Closing with a running queue asks as before and pauses it; closing with items that have not run asks first. `test_closing_with_a_waiting_queue_asks_first`. |

Also done, from the plan: an item that repeats an active one is refused
(`test_an_active_repeat_is_refused`); a waiting item can be removed while the queue
runs, and the running one cannot (`test_a_waiting_item_can_be_removed_while_the_queue_runs`);
the tab counts as busy for the whole run, so the Settings tab and the Viewer's
"Archive / copy" wait (`busy_changed` stays True between items in
`test_start_runs_the_items_in_turn`); the status text reads, for example, "queue 2 of
2, archiving 41 %".

## Decisions made

D81, "A queue in the Archive / copy tab". It closes O45 and O41.

## Changes after the work was committed

On 2026-10-21, while writing the manual checklist (`dev/v1.1-test/CHECKLIST.html`),
the agent found two faults in its own unmerged work and fixed them in a later commit
on this branch:

- The queue refused a second copy of a recording to another folder, because it
  treated "same recording, same operation" as a repeat for copies too. Copies now
  repeat only by destination; archives and Check archive still repeat by recording.
  Test: `test_two_copies_of_one_recording_to_two_folders_are_allowed`.
- The import message of a template (D80) wrote the field names in lower case, so "RF
  chain" read "rf chain". It now keeps their case: "Template loaded: Site, Project."

## Changes from the plan

- **The State column moved to second place.** In the first render it sat off the edge
  of the table. The column shows the state word and its mark; the full text is in the
  cell's tooltip and in a line under the table for the selected item.
- **Stop is hidden while the queue runs.** Pause takes its place. `stop()` pauses the
  queue, so closing the window works as before.
- **A check before delete that is stopped** marks the item Done with a note, since its
  archive passed. Start would otherwise try to archive an archived recording. The note
  asks the user to run the check from the form.
- **Add-time previews run only for items from the Viewer.** Items from the form passed
  their preview already.

## Code that copies, renames or deletes a file

None added. `transferqueue.run_item()` calls `preview_transfer()`, `run_transfer()`,
`check_before_delete()` and `check_archive()` unchanged, with the same arguments the
tab passes for one operation. The tab adds no file calls. `delete_laptop_copy()` is
not reachable from the queue. The table in [M6.md](M6.md), "Code paths that delete or
overwrite a file", with the changes in [M7.md](M7.md) and [M8.md](M8.md) part 2, is
unchanged. `test_architecture.py` passes.

## Not done in this piece of work

| Item | Where it lands |
| --- | --- |
| Saving the queue across a restart | Not planned for 1.1 (plan question 3; default: memory only) |
| A free-space check for the whole queue at Start | Each item checks its own at its run-time preview. Not planned. |
| Reordering items (move up or down) | Not planned; Remove and Add do it |

## Untested or not testable here

- The queue against the real NAS, and a Pause during a long archive there: agents use
  no network path. The tests run every step on real files under `tmp_path`.
- A pause across a long network outage: not testable here. The copy engine's retries
  (5 s apart) and Stop behave as for one operation.
- The Viewer's Ctrl and Shift selection by hand: the tests select rows through the
  selection model.

## Issues found in self-review

1. **A test left a question behind and hung the suite.** pytest-qt closes each window
   at teardown, after `monkeypatch` is undone; a window whose queue held a waiting item
   opened a real modal question. The two app tests now empty the queue. STATUS.md,
   "Notes for agents", records the trap.
2. **An item taken out for Edit and never added back is out of the queue.** The
   message line says that Add to queue puts it back. If the recording cannot be loaded,
   the item goes back by itself.
3. **The check mode of items from the Viewer** is the one chosen in the tab when they
   are added. A later change of the combo box does not change them. Edit does.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 1,709 passed, 4 skipped; clean |
| Queue two real archives to the NAS, Pause the first part-way, Start again, then delete each laptop copy | User | The queue on the real NAS and the pause on large files |

## Build output and files for the user to remove

`dev/o45-shots/`: the screenshot script, two screenshots and scratch databases. Listed
in STATUS.md.

## Recommendation and question

All five branches of the 1.1 plan are done. Merge `o20-freeze-schema-v1`,
`viewer-multi-filter`, `log-keep-fields`, `log-templates` and `transfer-queue` into
`main` as fast-forwards in that order? `transfer-queue` holds all of them, so one
fast-forward to it does the same. Then the release of 1.1.0 follows HANDOFF.md,
section 4.
