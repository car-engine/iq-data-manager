# The page after Add to queue, and "Forget" (O63, O64)

| | |
| --- | --- |
| Branch | `queue-actions`, from `queue-asks-for-folder` at `ad5b9d3` |
| Commits | The commit of this work and report |
| Tests | 2,005 passed, 4 skipped (`pytest`); `ruff check` clean |
| Report date | 2026-10-24 |
| Merge status | Not merged. The first of three branches after the manual test of 1.3.0. |

## Objectives against what was delivered

O63 and O64 came from the user's manual test of 1.3.0 (2026-10-24). The user answered
the plan on 2026-10-24: keep "Archive or copy" and allow a mixed selection, show the
page by a fixed order, and keep "Forget" without the dots.

| Objective | Status | Notes |
| --- | --- | --- |
| The page follows the action of the items added from the Viewer | Done | [transferqueue.py](../../src/iqdm/transferqueue.py) `page_after_add()`; [transfer_tab.py](../../src/iqdm/gui/transfer_tab.py) `_show_page_after_add()`. `test_the_page_after_an_add_follows_a_fixed_order` (seven cases), `test_the_page_follows_the_action_added_from_the_viewer`. |
| A fixed order for a selection that holds archives and copies | Done | A folder that items wait for first (NAS, then copies), then Archive, Copy, Check (D99). |
| "Forget" without the dots | Done | `test_forget_has_no_dots`. The user guide says what it keeps. |

## Decisions made

D99, "The page shown after Add to queue in the Viewer" (amends D98). D100, "'Forget'
under Unfinished transfers keeps its name".

## Changes from the plan

The plan recommended splitting the Viewer's menu into "Archive", "Copy" and "Check
archive". The user chose to keep "Archive or copy" with mixed selections (2026-10-24),
so the menu is unchanged and the page follows a fixed order.

## Code paths that delete or overwrite a file, or delete catalogue rows

None changed. "Forget" calls the same `forget_transfer()`, which sets
`transfer_log.dismissed_at` on one row and deletes nothing.

## Untested or not testable here

The page switch and the cursor in the folder field on a real display. The short manual
test after the three branches covers them.

## Issues found in self-review

1. **A change of page drops the form's preview.** Adding a copy from the Viewer while
   an archive preview stands on the Archive page now shows the Copy page, and the
   archive preview goes, as with any change of page (D96). The form is idle then, so
   nothing runs from it.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 2,005 passed, 4 skipped; clean |
| The short manual test after O60 to O62 | User | The page switch by eye |

## Build output and files for the user to remove

None.

## Recommendation and question

Continue with O60 and O61 on `transfer-field-marks`, from this branch.
