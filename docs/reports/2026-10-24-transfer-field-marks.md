# Frames on the Archive and Copy pages, and the Check page's line (O60, O61)

| | |
| --- | --- |
| Branch | `transfer-field-marks`, from `queue-actions` at `ce63581` |
| Commits | The commit of this work and report |
| Tests | 2,013 passed, 4 skipped (`pytest`); `ruff check` clean |
| Report date | 2026-10-24 |
| Merge status | Not merged. The second of three branches after the manual test of 1.3.0. |

## Objectives against what was delivered

O60 and O61 came from the user's manual test of 1.3.0 (2026-10-24). The user chose
amber for a field to fill in and red for a wrong value, and approved the Check page's
new line.

| Objective | Status | Notes |
| --- | --- | --- |
| Frame the field to fill in, before a preview (step 1.2) | Done | [movecopy.py](../../src/iqdm/movecopy.py) `form_marks()`; [transfer_tab.py](../../src/iqdm/gui/transfer_tab.py) `_show_field_marks()`, `_mark_field()`, `_mark_channels()`. `test_an_empty_destination_marks_the_folder_that_fills_it`, `test_the_archive_page_frames_the_field_to_fill_in`. |
| Frame the field behind a preview error | Done | `destination_errors()`. `test_a_preview_marks_the_destination_with_its_errors`, `test_errors_that_belong_to_no_field_give_no_mark`, `test_a_preview_error_frames_the_destination_in_red`. |
| Amber to fill in, red to correct | Done | The Log tab's `mark_style()` and `mark_colour()` (D95). `test_copy_fields_to_fill_in_or_correct`, `test_the_copy_page_frames_channels_and_times`. |
| No frame where nothing can be done | Done | `test_an_archived_recording_has_nothing_to_fill_in_on_the_archive_page`; the Check page clears every frame. |
| The Check page's line (O61) | Done | `CHECK_PAGE_PREVIEW`; `test_the_check_page_runs_no_transfer`. |

## Decisions made

D101, "The Archive and Copy pages frame the fields to fill in or correct".

## Changes from the plan

- **The channel boxes sit in a frame of their own** (`channels_frame`), with a
  transparent border while unmarked, so the layout does not move when the frame comes.
- **The folder frames of D98 and of D101 share one function.** An item that waits in
  the queue for a folder keeps its own placeholder ("Required for the items that wait
  in the queue"), which wins over the form's "(required)".

## Code paths that delete or overwrite a file, or delete catalogue rows

None. The branch changes how fields look.

## Untested or not testable here

The frames by eye on a real display, light and dark, and the channel frame's look. The
short manual test covers them.

## Issues found in self-review

1. **The frames are set on every button update.** `_mark_field()` sets a style sheet
   only when it changes, except after a switch of theme, so a keystroke repolishes no
   field whose frame stays.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 2,013 passed, 4 skipped; clean |
| The short manual test | User | The frames by eye |

## Build output and files for the user to remove

None.

## Recommendation and question

Continue with O62 on `quoted-names`, from this branch.
