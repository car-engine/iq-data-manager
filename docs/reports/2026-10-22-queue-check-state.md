# An archive whose check is still needed (open item O49)

| | |
| --- | --- |
| Branch | `queue-check-state`, from `log-message-states` at `9f37809` |
| Commits | The commit of this work and report |
| Tests | 1,761 passed, 4 skipped (`pytest`), `ruff check` clean |
| Report date | 2026-10-22 |
| Merge status | Not merged. This branch holds all of version 1.1. |

## Objectives against what was delivered

O49 came from the user's manual test of 2026-10-22, step 4.12: "Recordings 1,2,3 copy
passed, but verification failed. It was listed as failed though, which confused me."
The approved default, with the user's answer on Clear finished:

| Objective | Status | Notes |
| --- | --- | --- |
| A state ⓘ "Archived, check needed" in amber for a check that failed, was stopped or was skipped for "Sizes only" | Done, and for a check that could not run | [transferqueue.py](../../src/iqdm/transferqueue.py) `run_item`: `QueueState.CHECK_NEEDED`. `test_a_failed_check_before_delete_is_check_needed`, `test_a_stopped_check_before_delete_is_check_needed`, `test_sizes_only_skips_the_check_and_says_why`, `test_a_check_that_cannot_run_is_check_needed` (a read error, a refused file list). |
| The note: the recording points at the NAS copy, the laptop copy stays, run Check before delete in the form | Done | Same tests. |
| The summary counts it separately | Done | [transfer_tab.py](../../src/iqdm/gui/transfer_tab.py) `_finish_queue`: amber when only check-needed or not-started items remain. `test_an_archive_whose_check_is_needed_is_not_failed`. |
| Clear finished keeps such items; Remove removes them; Start skips them | Done | `test_clear_finished_keeps_archives_whose_check_is_needed`, and the tab test. |
| ✗ Failed stays for a copy or verification that failed | Done | Unchanged paths. |

## Decisions made

D85, "An archive whose check is still needed", which amends D81 and records the finding
below.

## Changes from the plan

- **A check that cannot run** also gives "Archived, check needed". Before, a read error
  or a refused file list during the check reached the tab as an exception, and the
  item showed ✗ Failed with the error text alone.
- **Edit is disabled** for these items: the archive is done, so the form's preview would
  refuse it.
- **The summary's parts are separated by ";"**, because the state's name holds a comma:
  "Queue finished. 1 done; 1 archived, check needed." An existing test changed with it,
  and a queue with items not started now ends amber, not green.
- **The note's wording** avoids "delete … from", which ruff's SQL check (S608) reads as
  SQL.

## The finding about the share of the same PC

Milestone 8 (part 2) recorded that Check before delete fails for every file read through
a Windows share of the same PC. In the user's test, arch_big (64,000-byte files, a
multiple of 512) passed its check through that share, and recordings 1 to 3 (4,000-byte
files) failed with WinError 87. The share most likely refuses reads past the cache of
files whose size is not a multiple of 512 bytes. The real NAS read 1,000,000-byte files
and a 500,000-byte last file in the field test of 2026-10-05, so it does not share the
limit.

Recorded in D85, STATUS.md ("Notes for agents", "Pending checks"), HANDOFF.md section 6
and a dated correction in [M8.md](M8.md). A new pending check: archive a recording with
its recorder logs on the real NAS, check it and delete the laptop copy (D83).

## Not done in this piece of work

| Item | Where it lands |
| --- | --- |
| "Check again" for these items | Not wanted for now (the user, 2026-10-22) |
| A probe that confirms the 512-byte rule on the share | Not needed for the app; the real NAS is the case that matters |

## Untested or not testable here

The queue against the real NAS. Tests force each way a check can fail.

## Issues found in self-review

None.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 1,761 passed, 4 skipped; clean |
| Step 4.11 to 4.13 of the manual checklist again, with "After each archive, run Check before delete" ticked | User | The amber state on a real display, with the share's known failure |

## Build output and files for the user to remove

None.

## Recommendation and question

Merge `queue-check-state` into `main` as a fast-forward (it holds all of version 1.1),
then release 1.1.0?
