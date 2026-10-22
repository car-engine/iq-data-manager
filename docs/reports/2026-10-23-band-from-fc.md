# The band filled in from fc (O50)

| | |
| --- | --- |
| Branch | `band-from-fc`, from `main` at `9403f46` |
| Commits | `9bfba8c`, plus the commit of this report |
| Tests | 1,837 passed, 4 skipped (`pytest`, 147.91 s); `ruff check` clean |
| Report date | 2026-10-23 |
| Merge status | Not merged |

The first piece of work for version 1.2, as in the plan the user approved on
2026-10-23. The user chose the band list on 2026-10-22 and changed it on 2026-10-23:
HF, VHF, UHF up to where L starts, then L, S, C, X, Ku and Ka. The agent proposed K
between Ku and Ka, and the user accepted it, with short names and fc as the
frequency on air.

## Objectives against what was delivered

O50 in STATUS.md asked the plan to settle these points: "what 'closest' means for
overlapping bands, where the band definitions live (settings are per PC, D68), and
what happens to a typed, kept or template band when fc changes." The prompt "Version
1.2" added edit mode and an fc in no band.

| Point | Status | Notes |
| --- | --- | --- |
| What "closest" means where bands overlap | Done | The narrowest band that holds fc; a tie goes to the band listed first ([bands.py](../../src/iqdm/bands.py), `band_for()`). The list of D88 has no overlaps. `test_the_narrowest_band_wins_where_bands_overlap` and `test_a_tie_goes_to_the_band_listed_first` use test lists with Marine VHF. |
| Where the definitions live | Done | Fixed in `bands.BANDS`, after IEEE Std 521, the same on every PC of one version. `test_the_list_runs_from_3_mhz_to_40_ghz_without_gaps_or_overlaps`, and one test per band edge. |
| A typed band | Done | It stays when fc changes, unless it equals the previous fc's band. An information line names an fc outside it. `test_a_band_the_user_chose_stays`, `test_follow_band`. |
| A kept band (D79) | Done | It follows the log's fc by the same rule. `test_the_logs_fc_moves_a_kept_band` repeats the 1.1.1 case (UHF kept, 145.8 MHz from the log, band VHF). `test_a_kept_band_that_differs_from_its_fc_stays`. A kept fc without a band fills the band: `test_a_kept_fc_without_a_band_fills_the_band`. |
| A template's band | Done | Applied after the template's fc, so it wins. A template channel with an fc and no band leaves the band to the rule. `test_a_templates_band_wins`. The D87 tests pass unchanged. |
| Edit mode | Done | Opening shows the stored band and changes nothing ("No changes to save."). Typing an fc applies the rule. `test_edit_mode_shows_the_stored_band`. |
| An fc in no band | Done | A band that followed fc is cleared; a band the user chose stays. `test_typing_fc_fills_the_band_in_italics`, `test_follow_band`. |
| fc as the frequency on air | Done | A down-converted fc typed over the log's moves the band from L to Ku and drops the log's mark. `test_a_down_converted_fc_typed_over_the_logs`. SPEC section 6 and the user guide say what fc means. |

Other changes on screen:

- A band filled in from fc is shown in italics, with the tooltip "Filled in from fc:
  VHF is 30 to 300 MHz. Pick or type another band to replace it." Otherwise the
  tooltip lists the bands. An offscreen probe (`dev/o50-probe/probe_italic.py`)
  confirmed that the style on the combo box reaches its text field.
- The box lists the ten bands in frequency order, then the catalogue's other bands
  (`entry.band_choices()`). `test_the_box_lists_the_bands_with_an_empty_catalogue`.
- The information line "Channel 0: fc 145.8 MHz is outside UHF (300 to 1000 MHz).
  Check the band." (`entry._band_items()`). It does not block saving:
  `test_the_band_line_does_not_block_saving`.
- `tests/test_user_text.py` checks both tooltips and the line
  (`test_band_text_is_plain`).

## Decisions made

- D88. The band filled in from fc. Amends D19.
- The index table of DECISIONS.md lacked rows for D86 and D87; both now have one.

## Changes from the plan

- Ranges are written "30 to 300 MHz" on screen and in the checklist. The plan wrote
  "30–300 MHz". Ruff refuses the en dash in source as an ambiguous character
  (RUF001), and the code writes other such characters as `\N{...}` escapes. "to" reads
  plainly and needs neither.
- A new entry's empty band takes the band of a kept or template fc when the channel
  rows are built. The plan named only changes of fc. Without this point, a kept fc
  without a band, or a template channel shown only after a later scan, left the band
  empty.
- `test_new_folder_keeps_format_channels_and_rf_chain` now expects UHF for channel 1.
  The test types 435 MHz over 145.8 MHz in a channel whose band is VHF, so the band
  follows (D88).

## Code paths that delete or overwrite a file, or delete catalogue rows

None changed.

## Untested or not testable here

- The italics and the tooltips by eye, in light and dark mode. The user checks these
  in the manual test of 1.2.
- Keyboard use of the band box (typing a part of a name, the completer). The tests
  type whole names.

## Issues found in self-review

1. **A band cleared on purpose comes back after a rescan of the same folder.** If
   the user empties the band of a new entry while fc stays, a rescan, or a change of
   the display offset, builds the rows again, and the empty band takes the band of
   fc. Left unchanged: the band then matches fc, and the user can type over it
   again. A band cannot be stored as "empty on purpose" without a flag that survives
   the rebuild.
2. **Each key typed in fc moves the band.** Typing 433 passes "43" (VHF) before
   "433" (UHF). The band ends right, because the band of each step follows the next.
   A band the user chose before typing fc is never moved.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| Manual test of 1.2: a recorder folder, a kept band, a template, edit mode, light and dark mode | User | The screen by eye, with the HTML checklist under `dev/` before the release |

## Build output and files for the user to remove

- `dev/o50-probe/` (the italic probe script).

## Recommendation and question

Continue with O39 on `delete-entry`, from this branch. Merge both after the manual
test of 1.2.
