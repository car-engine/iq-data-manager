# The Log tab's message line shows its state (open item O48)

| | |
| --- | --- |
| Branch | `log-message-states`, from `transfer-log-files` at `2574beb` |
| Commits | The commit of this work and report |
| Tests | 1,755 passed, 4 skipped (`pytest`), `ruff check` clean |
| Report date | 2026-10-22 |
| Merge status | Not merged |

## Objectives against what was delivered

O48 came from the user's manual test of 2026-10-22, notes for section 3: "The expected
outputs are all with white font. Should have some colouring (red/yellow/green that has
already been used) to indicate success/warning/failure." The approved default: give each
message on the Log tab's line a mark and the checklist's colours, in light and dark
mode; "Saving..." stays plain.

| Objective | Status | Notes |
| --- | --- | --- |
| A mark and colour for each message | Done | [log_tab.py](../../src/iqdm/gui/log_tab.py): `show_message(text, state)`; every call names its state (list in D84). `message_text` gives the text without the mark. |
| The checklist's colours in light and dark mode | Done | `colours_for(palette)`; restyled on a theme switch. `test_messages_show_their_mark_and_colour` (both themes), `test_the_message_colour_follows_a_theme_switch`. |
| "Saving..." plain | Done | `test_a_message_without_a_state_is_plain`. |

## Decisions made

D84, "The Log tab's message line shows its state".

## Changes from the plan

- Messages for something still to do (no database; choose a folder first; complete the
  checklist first) use the grey ○ of the checklist's to-do items. The plan named three
  states only.
- 32 test assertions now read `message_text` in place of the label's text, which now
  starts with the mark.

## Not done in this piece of work

None.

## Untested or not testable here

The colours were checked in tests against the light and the dark colour sets. The look
on a real display in Windows dark mode is the user's.

## Issues found in self-review

None.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 1,755 passed, 4 skipped; clean |
| Steps 3.3 to 3.9 of the manual checklist again | User | The marks and colours on a real display |

## Build output and files for the user to remove

None.

## Recommendation and question

Continue with O49 on `queue-check-state`.
