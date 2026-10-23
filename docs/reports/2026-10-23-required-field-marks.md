# Fields to fill in or correct are framed (O54)

| | |
| --- | --- |
| Branch | `required-field-marks`, from `logged-by-typed` at `07c6e18` |
| Commits | The commit of the code and this report |
| Tests | 1,958 passed, 4 skipped (`pytest`, 138.16 s); `ruff check` clean |
| Report date | 2026-10-23 |
| Merge status | Not merged |

The fourth and last piece of work for version 1.2.1. Team feedback on 1.2: when a
mandatory field was not filled in, the only signs were the checklist and the disabled
Save button. The user approved the plan on 2026-10-23 and chose an amber frame with
"Required" for an empty field and a red frame for a wrong value.

## Objectives against what was delivered

O54's proposed default: "An empty required field gets an amber frame and the
placeholder 'Required'; a wrong value gets a red frame with the reason as its
tooltip."

| Point | Status | Notes |
| --- | --- | --- |
| One rule for the checklist and the frames | Done | `entry.field_marks()` in [entry.py](../../src/iqdm/entry.py); `_required_items()` and `_param_items()` now build their lines from it, and the existing checklist tests pass unchanged. Tests: `test_a_filled_form_has_no_field_marks`, `test_empty_required_fields_are_to_do`, `test_wrong_values_are_errors_with_their_reason`, `test_rf_chain_rows_are_marked_by_their_position`, `test_every_blocking_checklist_line_about_a_field_has_a_mark` (three forms). |
| Amber frame and "Required" on an empty field | Done | Logged by, site, fc, fs, and an RF chain row's name and value ([log_tab.py](../../src/iqdm/gui/log_tab.py), `mark_style()`, `_show_mark()`, `LogTab._show_field_marks()`). Tests: `test_empty_required_fields_are_framed`, `test_rf_chain_rows_are_framed`. |
| Red frame and the reason on a wrong value | Done | fc, fs, and an RF chain row's channel. Tests: `test_a_wrong_value_is_framed_with_its_reason`, `test_an_rf_chain_row_on_a_missing_channel_is_framed`. |
| With the italics of a filled-in value | Done | `test_a_mark_keeps_the_italics_of_a_value_from_the_log`; the fs filled in from the file size in `test_empty_required_fields_are_framed`. |
| In both themes | Done | `test_the_frames_follow_a_theme_switch`. See "Found while testing". |
| "Several folders" | Done | The shared fields and the selected folder's channels. `test_the_shared_fields_and_the_selected_folders_channels_are_framed`. |
| The disabled Save button says why | Done | Tooltip 'Complete the items under "Before saving" first.' (with the quotes since the manual test, below) `test_the_disabled_save_button_says_why`. |

The new texts are in `test_log_tab_text_is_plain` in `tests/test_user_text.py`.

## Found while testing

A widget with a style sheet keeps the palette it had when the sheet was set. A probe
(`dev/o54-debug.py`) showed a framed Logged by field still at the light background,
`#ffffff`, after a switch to the dark palette, while a field without a sheet followed
(`#2d2d2d`). Setting the sheet again makes the widget take the new palette. After a
theme switch, the Log tab therefore sets each field's sheet again
(`_restyle_sheets()`), and the frame's colour comes from the application's palette.
The italic fields of D21, D82 and D88 had the same stale background after a switch
before this change; they now follow too. The user runs Windows in dark mode, so this
showed only when the theme changed while the app ran.

## Decisions made

- D95. Fields to fill in or correct are framed. Amends D23. D94's placeholder became
  "Your name (required)".

## Changes after the user's review

The user ran the manual test of 1.2.1 on 2026-10-23 (`dev/test-1.2.1/CHECKLIST.html`,
build `dist/test-1.2.1` from `b29c497`): 26 of 28 steps passed, step 1.3 failed and
the optional step 1.7 (a touchpad) was not run.

- **Step 2.1:** the user asked that the tooltip mark "Before saving" as the name of
  something on the screen. It now reads 'Complete the items under "Before saving"
  first.', as other texts quote a group's name ("Unfinished transfers"). Changed in
  the commit after `b29c497`.
- **Step 1.3** ("An open list still scrolls") failed: the open band list did not
  scroll. A probe with the `windows11` style (`dev/o56-popup/probe.py`) showed that
  the band list holds 10 entries, and a dropdown shows 10 before it needs a scroll
  bar, so its scroll range is 0 to 0; a list of 30 entries scrolled with the guard
  installed (value 0 to 3). The step tested a list that cannot scroll; the app
  needs no change. See the 1.2.1 summary for a repeat of the step.
- **Step 4.2:** the user asked why the framed dropdown looks different. Answered in
  chat; see "Issues found in self-review", item 1.

## Changes from the plan

- The placeholders hold "Required" in a form that suits each field: "Your name
  (required)", "Choose a site (required)", "Required" for fc and the RF chain fields,
  and "Required, e.g. 10M" for fs. The plan named "Required" alone.
- `_restyle_sheets()` was not in the plan; "Found while testing" gives the reason.

## Code paths that delete or overwrite a file, or delete catalogue rows

None.

## Untested or not testable here

- The look of a framed dropdown under the real Windows 11 style. Offscreen, the
  `windows11` style in the dark palette drew the frames clearly, but the framed site
  dropdown drew Qt's own arrow in place of the Windows 11 one. Offscreen renders in
  the light palette and with `windowsvista` drew buttons and dropdowns black or
  blank, with or without a frame, so they show nothing about this change. The user
  checks the screen in the manual test.
- A theme switch while the app runs, on Windows itself. The test switches the
  application palette.

## Issues found in self-review

1. **A framed dropdown looks a little different from the others** (see above). Left
   as it is; D95 records it. A frame drawn without a style sheet would need a custom
   paint of every field type.
2. **The frames follow the checklist's refresh,** 150 ms after typing stops, as the
   checklist does.
3. **I wrote `dev/o54-debug.py` once with a heredoc** that left it empty, then wrote
   its content with the Write tool. The project's rules say to write files only with
   Write and Edit. The file is under `dev/`, which is gitignored.
4. **`entry.py`, `log_tab.py` and the test files are not in `ruff format` style**, as
   before. The new lines follow the wrapping of the code around them.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| The manual test of 1.2.1: the frames on an empty form, after a scan, with a wrong fs, with an RF chain row half filled, in "Several folders", and in dark mode | User | The look by eye under the real Windows 11 style |

## Build output and files for the user to remove

- `dev/o54-debug.py` and `dev/o54-shots/` (probe and screenshot scripts). The renders
  are in the session's scratch folder under `%TEMP%\claude\` (`o54-win11-light`,
  `o54-win11-dark`, `o54-vista-light`).

## Recommendation and question

Version 1.2.1 is complete on four branches: `wheel-guard`, `batch-log-rf-rows`,
`logged-by-typed` and `required-field-marks`, each from the one before. Next: the
manual test of 1.2.1 on a test build, then a fast-forward merge into `main` and the
release, each with the user's approval.
