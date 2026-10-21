# Values from the recorder's log (open item O46)

| | |
| --- | --- |
| Branch | `recorder-log-fill`, from `transfer-queue` at `c0252f9` |
| Commits | The commit of this work and report |
| Tests | 1,741 passed, 4 skipped (`pytest`), `ruff check` clean |
| Report date | 2026-10-21 |
| Merge status | Not merged. Merge after `transfer-queue`, as a fast-forward. |

## Objectives against what was delivered

O46 in `docs/STATUS.md` read: "Fill Log tab fields from the recorder's log files after
a scan". Its default, approved on 2026-10-21, was: "Read `recorder_*.log`, falling back
to `log.txt`; match by channel number ("Using channel N" = folder N). Fill fc and fs
per channel, sample type (sc16 → int16, sc8 → int8, fc32 → float32), "USRP Gain" in dB
(one Recording row when all channels match), "Clock reference" (GPSDO, Internal,
External), and "USRP" from the log only when the form has no USRP row. Filled values
are marked and stay until typed over; log values take precedence over kept and
template values; edit mode never replaces stored values. Information lines (not
blocking): the recorder's verdict, GPS lock, a PC-clock time source, a file count that
differs from the recorder's. An unreadable log fills nothing. Top-level `*.txt` and
`*.log` are no longer "not recognised"."

| Objective | Status | Notes |
| --- | --- | --- |
| Read `recorder_*.log`, falling back to `log.txt` | Done | [recorderlog.py](../../src/iqdm/recorderlog.py) `read_folder`, `parse_main_log`, `parse_command_line`, `parse_check`. Both of the user's examples parse: `test_the_one_channel_example`, `test_the_two_channel_example`, `test_the_command_line_alone`. |
| Match by channel number | Done | `test_a_channel_folder_named_after_the_usrp_channel`, `test_four_twinrx_channels`, `test_only_the_scanned_channels_are_filled`. |
| fc, fs, sample type, USRP Gain, Clock reference, USRP only when none | Done | `form_values`, `merge_params`. `test_form_values_of_the_two_channel_example`, `test_different_gains_give_a_row_per_channel`, `test_a_usrp_row_already_in_the_form_stays`, `test_sample_formats`. In the tab: `test_a_scan_fills_values_from_the_recorder_log`. |
| Marked until typed over; precedence over kept and template values | Done | [log_tab.py](../../src/iqdm/gui/log_tab.py) `_apply_recorder_log`, `_mark_fc`, `_mark_fs`. `test_the_log_replaces_kept_values_but_not_a_usrp_row`, `test_typing_ends_the_mark_and_a_rescan_does_not_fill_again`. |
| Edit mode never replaces stored values | Done | `test_edit_mode_reads_the_log_but_fills_nothing`. |
| Information lines, not blocking | Done | `checklist_items`. `test_no_line_blocks_saving`, `test_the_file_count_differs`, `test_a_file_count_that_differs_does_not_block_saving`. |
| An unreadable log fills nothing | Done | `test_a_log_too_large_is_not_read`, `test_several_logs_and_none_named_after_the_folder`. |
| Top-level `*.txt` and `*.log` no longer "not recognised" | Done | [scanner.py](../../src/iqdm/scan/scanner.py): `ScanResult.side_files`. `test_txt_and_log_files_at_the_top_are_side_files`. |

## Decisions made

D82, "Values from the recorder's log".

## Changes from the plan

- **Filled once per folder.** A rescan of the same folder does not fill again, so an
  edit made after the first scan stays. The plan said only "stay until typed over".
  RF chain rows have no per-row typing state, so filling once is the rule that keeps
  them too.
- **The junk file of the fixture generator** was `notes.txt` at the top of the folder.
  That name is now a side file, so the generator writes `notes.md`. Three tests that
  named it changed with it.
- **The scanner lists side files with their sizes.** The plan put this in O47. O46
  needed the names, and the sizes come from the same directory listing.

## Not done in this piece of work

| Item | Where it lands |
| --- | --- |
| Copying the log files with the recording | O47, the next branch, `transfer-log-files` |
| Telling a USRP-2954 from an X310 with UBX boards | Needs the recorder to log the motherboard's serial number or product name; the template keeps "USRP-2954" meanwhile |

## Untested or not testable here

- The parser was tested on the two real examples and on logs written in their format.
  Another recorder build that changes a line's wording fills nothing for that value;
  the tests would not catch such a change in advance.
- A real TwinRX log was not available. Its four channels were tested with a log written
  in the format of the UBX examples, with "TwinRX RX0" as the subdevice name.
- The Log tab was rendered offscreen in the light and a dark palette (`dev/o46-shots/`).

## Issues found in self-review

1. **"Files written" counts every channel.** In the two-channel example it is 540, the
   total over both channels. The cross-check compares it with the total the scan finds,
   so it holds for any number of channels.
2. **The device summary lists every channel of the USRP**, recorded or not. The parser
   keeps only the channels that have a "Using channel" block, so an unused daughterboard
   does not appear in the "USRP" value.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 1,741 passed, 4 skipped; clean |
| Log a real recording made by the recorder, with its log files, in the 1.1 build | User | The values on real data, and whether the information lines help |

## Build output and files for the user to remove

`dev/o46-shots/`. Listed in STATUS.md, with `recorder/` at the repository root, which
holds the user's examples and is not tracked.

## Recommendation and question

Continue with O47 on `transfer-log-files`, which copies these log files with the
recording.
