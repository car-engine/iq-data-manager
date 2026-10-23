# Names of controls in quotation marks (O62)

| | |
| --- | --- |
| Branch | `quoted-names`, from `transfer-field-marks` at `e9cdccf` |
| Commits | The commit of this work and report |
| Tests | 2,014 passed, 4 skipped (`pytest`); `ruff check` clean |
| Report date | 2026-10-24 |
| Merge status | Not merged. The last of three branches after the manual test of 1.3.0; it holds all of 1.3.0. |

## Objectives against what was delivered

O62 came from the user's manual test of 1.3.0 (2026-10-24, step 2.1) and a note after
it: "Names of fields/buttons - "Run copy", "Preview" etc. all should be in quotes to
differentiate it as a noun rather than just a word." The user chose to drop the "..."
of a quoted name and to keep bold in the user guide.

| Objective | Status | Notes |
| --- | --- | --- |
| Quotes round the names of controls in the text of every tab | Done | About 70 texts in `app.py`, the four tabs, `entry.py`, `movecopy.py`, `transferqueue.py`, `viewer.py`, `batchlog.py`, `db/repository.py`, `transfer/operations.py` and `transfer/pathcheck.py`. |
| No trailing "..." in a quoted name | Done | For example "Delete laptop copy". |
| A check in `tests/test_user_text.py` | Done | `unquoted_names()`, called by `offending()` for every text the module collects; the names are in `tests/user_text_names.py`. `test_names_in_a_sentence_need_quotes`. |
| The user guide keeps bold | Done | No change to the guide in this branch. |

## Decisions made

D102, "Names of controls in quotation marks" (amends D38).

## How the texts were found

`dev/o62/names.py` built the main window offscreen and listed 109 control names.
`dev/o62/scan.py` read every string constant of `src/iqdm` with `ast`, so that adjacent
literals and f-strings are joined as Python joins them, and listed the 276 constants
that held a name outside quotes. Most were ordinary words at the start of a sentence
("Archive it to the NAS first.", "Recording 12 is …"), labels, or window titles. The
rest were edited; a second scan left 171 constants, all of those kinds. A `grep` for
"Log tab" found the references to the "Log recording" tab, which the scan could not
know.

## Changes from the plan

- **A few texts were reworded to name the control** (D102 lists them), for example
  "Preview it again." became 'Click "Preview" again.'
- **"the Log tab" became 'the "Log recording" tab'**, the tab's real name.
- **The dialog title "Delete entry?" became "Delete this entry?"**, so that the title
  reads as a question and not as a button's name.
- **The automated check leaves out names that are also ordinary words** ("Archive",
  "Check", "Copy", "Save", "Start", "Site", "RF chain" and others; the list is in
  `tests/user_text_names.py`). It cannot tell 'click "Save"' from "Save the settings".
  Those were reviewed by hand.

## Code paths that delete or overwrite a file, or delete catalogue rows

None. Text only.

## Untested or not testable here

Every text on a real display, in light and dark mode. The second manual test reads
each tab.

## Issues found in self-review

1. **A test that fails while the queue holds an item hangs the suite.** The first full
   run after the edits hung:
   `test_app_smoke.py::test_the_queue_holds_a_recording_against_a_delete` failed on
   the old text before it removed its queue item, and the window's teardown then asked
   a real question (STATUS.md, "Notes for agents"). The run ended at its `timeout`.
   Fixed by updating the expected text; the note in STATUS already describes the trap.
2. **The console program and the test-set notes it writes** keep their texts. They name
   no control of the window, and the team reads them in a console.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 2,014 passed, 4 skipped; clean |
| The second manual test of 1.3.0 | User | The texts and the changes of O60 to O64 on a real display |

## Build output and files for the user to remove

`dev/o62/` (the two scripts, `run1` with its scratch catalogue, and the scan outputs),
listed in STATUS.md.

## Recommendation and question

Run the second manual test. If it passes, merge `quoted-names` into `main` as a
fast-forward (it holds all of 1.3.0) and release 1.3.0?
