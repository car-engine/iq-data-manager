# A new folder keeps the previous entry's fields (open item O43)

| | |
| --- | --- |
| Branch | `log-keep-fields`, from `viewer-multi-filter` at `1e212f6` |
| Commits | The commit of this work and report |
| Tests | 1,631 passed, 4 skipped (`pytest`), `ruff check` clean |
| Report date | 2026-10-20 |
| Merge status | Not merged. Merge after `viewer-multi-filter`, as fast-forwards in order. |

## Objectives against what was delivered

O43 in `docs/STATUS.md` read: "A new Log tab entry keeps the fields of the previous
one. Only the values that come from the scan are reset." Its proposed default,
approved on 2026-10-20, was: "Keep logged by, site, project, plan reference, remarks,
sample type, IQ layout, endianness, header bytes, band and fc per channel number, and
the RF chain rows. Reset start and end, file counts, fs (filled in again from the
scan, D21) and file duration (set again from the file names, D22). A note in the
"Before saving" panel lists the kept format values. After a scan, settings for
channels the new folder lacks are removed, and the message line names them. Clear
form still resets everything. Replaces D26."

| Objective | Status | Notes |
| --- | --- | --- |
| Keep the typed fields | Done | [log_tab.py](../../src/iqdm/gui/log_tab.py): `_folder_changed` calls `_reset_scan_fields` in place of the D26 reset. Band and fc wait in `_carried` by channel number. `test_new_folder_keeps_format_channels_and_rf_chain`, `test_typing_a_folder_keeps_the_rf_chain`. |
| Reset start, end, counts, fs and file duration | Done | fs is filled in again for the kept sample type, in italics; the duration comes from the new file names. Same tests. |
| A note in the "Before saving" panel | Done | `kept_note`, with the information mark and colour. Text from `entry.kept_note()`. Shown only when something other than the defaults was kept, hidden after Clear form and in edit mode. `test_clear_form_drops_the_kept_values`, `test_no_note_when_nothing_but_defaults_is_kept`, `test_edit_mode_shows_no_kept_note`. |
| Remove settings of channels the new folder lacks, and name them | Done | `_drop_settings_of_missing_channels`, text from `entry.missing_channels_text()`. `test_values_of_channels_the_new_folder_lacks_are_removed`. |
| Clear form resets everything | Done | `_reset_all_fields`. |
| Replaces D26 | Done | D79; D26 marked "Replaced by D79". |

## Decisions made

D79, "A new folder keeps the previous entry's fields".

## Changes from the plan

- The plan's note text started "Kept from the previous entry: int8, ..." without a
  mark. The note now carries the information mark and colour, so it follows
  CLAUDE.md, "User-facing text": a state shown by colour and by a mark.
- The checklist change sits in `entry.checklist()`: before the first scan of a new
  entry it passes no channel list to `_param_items`, which then skips the channel
  check. The plan named `_param_items` only.
- `test_rf_chain_names_take_the_stored_spelling` logged two folders in a row and
  relied on the RF chain being reset between them. It now clears the kept row before
  it adds its own. The test still checks the stored spelling (D28).

## Not done in this piece of work

| Item | Where it lands |
| --- | --- |
| Templates (import and export) | O44, the next branch, `log-templates` |

## Untested or not testable here

- The note was checked in offscreen renders with the light palette and a dark palette
  (`dev/o43-shots/`). The look in Windows dark mode by eye is the user's.
- Logging several real folders in a row with the 1.1 build is the user's check.

## Issues found in self-review

1. **The combo boxes return the format enums as plain text.** The first version of
   `has_kept_values` compared with `is not` and saw every form as changed. It now
   compares with `!=`, and a test covers plain text. STATUS.md, "Notes for agents"
   already describes this trap for `QComboBox` and `StrEnum`.
2. **A kept `int8` fills in fs for `int8` in the next folder.** That risk was the
   reason for D26. D79 records it. The note names the kept sample type, and the
   checklist names the basis of each filled-in fs.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 1,631 passed, 4 skipped; clean |
| Log two or three real folders in a row in the 1.1 build | User | The time saved, and whether the note is clear |

## Build output and files for the user to remove

`dev/o43-shots/`: the screenshot script, two screenshots, and `run-*` folders with
synthetic recordings and scratch databases. Listed in STATUS.md.

## Recommendation and question

Merge after `viewer-multi-filter`. The next branch, `log-templates` (O44), starts from
this one.
