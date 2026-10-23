# The mouse wheel never changes a field (O56)

| | |
| --- | --- |
| Branch | `wheel-guard`, from `main` at `f22bc20` |
| Commits | The commit of the code and this report |
| Tests | 1,932 passed, 4 skipped (`pytest`, 161.25 s); `ruff check` clean |
| Report date | 2026-10-23 |
| Merge status | Not merged |

The first piece of work for version 1.2.1. Team feedback on 1.2: while the user
scrolled a tab with the mouse wheel, the pointer often passed over a dropdown or a
number field, and the wheel changed it. The user approved the plan on 2026-10-23 and
chose "never change a field" over "change it only after a click".

The same session recorded O53 to O59 in STATUS.md, from the same feedback. O57 to
O59 (the Archive / copy tab) are for version 1.3.0 and another session.

## Objectives against what was delivered

O56's proposed default: "The wheel never changes a dropdown or number field anywhere
in the app; it scrolls the page."

| Point | Status | Notes |
| --- | --- | --- |
| No dropdown or number field changes on the wheel | Done | `WheelGuard` in [wheel_guard.py](../../src/iqdm/gui/widgets/wheel_guard.py) keeps wheel events from every `QComboBox` and `QAbstractSpinBox`, which covers `CheckComboBox`, `QSpinBox` and `QDoubleSpinBox`. Tests: `test_the_wheel_leaves_a_dropdown_unchanged`, `test_the_wheel_leaves_number_fields_unchanged`, `test_the_wheel_leaves_a_tick_box_list_unchanged`; the control case without the guard, `test_without_the_guard_the_wheel_changes_the_fields`. |
| Anywhere in the app | Done | The filter sits on the `QApplication`, installed once by `MainWindow` ([app.py](../../src/iqdm/app.py)). Tests: `test_install_adds_one_guard`, `test_the_main_window_installs_the_guard` (the Log tab's sample type keeps its value). |
| The page scrolls | Done, tested by hand only | The filter leaves the event unaccepted. Qt's `QApplication::notify` then passes a real wheel event to the parent widgets until one accepts it, such as the scroll area of the form or a table. Other widgets get the wheel as before: `test_other_widgets_still_get_the_wheel`. A test cannot send a real wheel event, so the scroll is a step of the manual test. |

The fields still change by a click on their list, by their arrows and by the arrow
keys. An open dropdown list is a separate widget and still scrolls.

## Decisions made

- D92. The mouse wheel never changes a field.

## Changes from the plan

None.

## Code paths that delete or overwrite a file, or delete catalogue rows

None.

## Untested or not testable here

- The scroll of the page when the wheel turns over a field. Qt passes an unaccepted
  wheel event to the parent only for real input, and a test sends its events itself.
  The user checks it in the manual test of 1.2.1, with a mouse and with a touchpad
  if a laptop has one.

## Issues found in self-review

1. **`app.py` is not in `ruff format` style.** It was not before this change either.
   The file was left as it was (STATUS.md, "Notes for agents").

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| The manual test of 1.2.1: the wheel over the Log tab's fields, the channel table, the RF chain table and the Settings tab scrolls the page and changes nothing | User | The scroll needs real input |

## Build output and files for the user to remove

None.

## Notes for version 1.3.0 (O57 to O59)

The session's plan covered the team's feedback on the Archive / copy tab too. The user
answered part of it on 2026-10-23 and gave the rest to a later session for version
1.3.0. These notes record the plan as it stood, for that session.

**Severity.** O59 (adding from the Viewer without a folder) is medium: every overnight
batch meets it. O57 (no check after an archive) is medium to low: Delete laptop copy
stays blocked until a check passes, so the cost is time. O58 (the cluttered tab) is a
low risk and a large change. A version 1.3.0 is warranted: the three change the
screen and the steps of every archive, so USER_GUIDE.md section 5 needs a rewrite and
a manual test of its own.

**Proposed branches**, each from the one before: `transfer-pages` (O58),
`check-after-archive` (O57), `queue-asks-for-folder` (O59).

**O57, the check after an archive.** In 1.2.0 the queue runs Check before delete after
each archive when "After each archive, run Check before delete" is ticked
(`transferqueue.run_item()`); Run archive in the form does not. The user's case was a
queue run with Compare at hashes of 0.5 % of the files, and the box was perhaps not
ticked. The user chose a check straight after each archive, from the form and the
queue, and asked that the box be removed. The reasons given in the plan: if the queue
stops part-way through the night, the archives before the stop are already checked;
the per-item states of D85 stay; a check at the end of the queue gives the NAS
longer to drop its own cache, but only for the early items, and the check already
reads past this PC's cache (D55). The plan moves the check-after code out of
`run_item()` into one function that Run archive also calls in its worker. Still to
decide: an archive with "Sizes only", for which Check before delete cannot run.

**O58, the pages.** The user found this layout fine for now:

```
┌──────────────────────────────────────────────┬─────────────────────┐
│ Recording ID [ 12 ] [Load] [Pick in Viewer]  │ Preview             │
│ 12 · 2026-10-20 08:00 (UTC+8) · Site A · 2 ch│  Files … Size …     │
│ ┌ Archive ┬ Check ┬ Copy ┐                   │  checklist lines    │
│ │ NAS folder for archives [__________][…]    │  file list          │
│ │ Destination  <NAS folder>\day1\rec01       │ [Preview][Run       │
│ │ Compare  [Sizes, and hashes of 10 % ▾]     │  archive][Add to    │
│ │ ── Laptop copy ──                          │  queue][Stop]       │
│ │ state  [Check before delete] [Delete…]     │  progress, result   │
│ └────────────────────────────────────────────┘                     │
├──────────────────────────────────────────────┴─────────────────────┤
│ ┌ Queue (3) ┬ Unfinished transfers (1) ┐                             │
│ │ table …               [Start][Pause][Edit][Remove][Clear finished]│
└─────────────────────────────────────────────────────────────────────┘
```

The page sets the operation, in place of the Copy and Archive radio buttons. The
Archive page holds one "NAS folder for archives", shared with the items added from
the Viewer, and a destination filled as that folder plus the relative path. The Copy
page holds the scope, the channels, the timeline and a "Folder for copies" that
starts from Settings. The Check page holds Check archive and Compare with laptop
copy. The pages are locked while an operation runs. The plan's open questions, which
the user left for the 1.3 session:

1. Check before delete and Delete laptop copy on the Archive page, and Check archive
   and Compare with laptop copy on the Check page (recommended).
2. The page that the Viewer's "Archive / copy" button opens. Recommended: Archive for
   a laptop recording, and for an archived one whose laptop copy the app archived and
   has not deleted; Copy for any other archived recording.
3. The tab's name. Recommended: keep "Archive / copy".

Moving Delete laptop copy to another page changes no code path that deletes a file:
`start_delete()`, its question (default No) and its rule (a passed Check before
delete, D55) stay. The report of that branch lists it.

**O59, the folder for the queue.** `transferqueue.item_for_recording()` refuses an
archive without a NAS folder and a copy without a default copy folder. The plan: the
items join the queue as "○ Needs a NAS folder" or "○ Needs a copy folder"; the tab
opens the page with the missing field and marks it; choosing the folder fills in
each waiting item's destination and previews it; Start stays disabled while an item
waits; `run_item()` refuses an item without a destination before it previews. Not
yet discussed with the user: whether items wait in the queue or the selection waits
on the page, and whether Start runs the other items meanwhile.

## Recommendation and question

Continue with O55 (the log rows in "Several folders") on a branch from this one.
