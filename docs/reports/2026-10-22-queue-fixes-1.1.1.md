# Queue fixes for 1.1.1

| | |
| --- | --- |
| Branch | `queue-fixes-1.1.1`, from `review-1.1.0` |
| Commits | `1f736ea`, plus the commit of this report |
| Tests | 1,771 passed, 4 skipped (`pytest`, 125.92 s); `ruff check` clean |
| Report date | 2026-10-22 |
| Merge status | Not merged |

The first of two branches for version 1.1.1. It fixes findings 1, 5, 6 and 10 of the
[review of 1.1.0](2026-10-22-review-1.1.0.md), as in the plan the user approved on
2026-10-22. The user also asked that the queue's Start button read Resume while an
item is paused.

## Findings against what was delivered

| Finding | Status | Notes |
| --- | --- | --- |
| 1. A database error in Check before delete after a passed archive showed ✗ Failed | Done | `run_item()` turns every error of that step into "Archived, check needed" ([transferqueue.py](../../src/iqdm/transferqueue.py)). `test_a_check_that_cannot_run_is_check_needed` gains `DatabaseBusyError`, `DatabaseError` and `RuntimeError`; `test_a_locked_database_after_a_passed_archive_is_check_needed` runs it through the tab and checks the amber summary. |
| 10. A paused queue item could also be finished with the form's Run | Done (D86) | `TransferQueue.holding()` finds the active item that the form's transfer repeats, by the queue's repeat rule. Run and Add to queue stay off for it, and `queued_label` says why ([transfer_tab.py](../../src/iqdm/gui/transfer_tab.py)). `start_run()` refuses it when called directly. The end of a queue run drops the form's preview. Tests: `test_holding_finds_the_item_a_form_run_would_repeat`, `test_a_paused_item_continues_only_in_the_queue`, `test_resume_from_unfinished_transfers_points_at_the_queue`, `test_a_waiting_item_is_not_run_from_the_form`. |
| The Start button reads Resume (the user's request) | Done (D86) | `TransferQueue.has_paused()`. The pause question, the end-of-queue summary ("Queue paused. 1 left; Resume continues.") and a paused item's note name Resume. `test_pause_then_start_finishes_the_item` checks both labels; `test_has_paused`. |
| 5. The Pause question promised more than a pause during the check gives | Done | The question says that the check stops and the item becomes "Archived, check needed". The user guide says the same. The text is in `test_queue_text_is_plain`. |
| 6. After a dropped Edit, a later Add to queue took the edited item's place | Done | `_edit_position` is cleared when another recording is loaded, when the form runs the transfer, and when the form is cleared. `test_an_edit_dropped_for_another_recording_frees_its_place` (the review's probe). |

## Decisions made

- D86. A paused queue item continues in the queue only. Amends D81.

Finding 1 makes the code do what D85 already states ("a check that could not run"),
so it needs no new decision.

## Changes from the plan

- The plan said Resume under "Unfinished transfers" would be refused. It still loads
  and previews the transfer, as before; Run then stays off with the line that names
  the queue. That shows the user where the transfer is, instead of a refusal with no
  form.
- `test_add_to_queue_from_the_form` now expects Add to queue to be disabled for a
  transfer the queue holds, and calls `add_current_to_queue()` directly to check the
  queue's own refusal.

## Code paths that delete or overwrite a file

None changed. The branch changes when the form may start a transfer, not how a
transfer copies.

## Untested or not testable here

- The new line under the buttons and the Resume label by eye, in light and dark
  mode. The user checks these in the manual test of 1.1.1.

## Issues found in self-review

None.

## Recommendation

Continue with the second branch, `log-fixes-1.1.1`. Merge both after the user's
manual test.
