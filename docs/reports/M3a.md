# Milestone 3a: Settings tab

| | |
| --- | --- |
| Branch | `m3a-settings` |
| Commits | `8298a97` to `a7e647f` (5 commits), plus the commit that adds this report and the documentation |
| Tests | 728 passed, 2 skipped (`pytest`), `ruff check` clean |
| Report date | 2026-10-02 |
| Merge status | Not merged |

## Objectives against what was delivered

SPEC section 12 defines this milestone as: "**Settings tab** (brought forward from
Milestone 7; DECISIONS.md D29): config writer, Settings tab with database status and
check, NAS roots and display offset, applying changes without a restart, tests (scope
narrowed by D30)."

| Objective | Status | Notes |
| --- | --- | --- |
| config writer | Done | [config.py](../../src/iqdm/config.py): `save_config()` writes with `tomli-w` (D31). It checks the data with `parse_config()`, reads the text back, writes `config.toml.new`, copies the old file to `config.toml.bak` (D35) and then replaces `config.toml`. `merge_settings()` keeps every key that the tab does not show. `settings_errors()` and `hidden_key_error()` use the same rules as `parse_config()`. |
| Settings tab with database status and check | Done | [settings_tab.py](../../src/iqdm/gui/settings_tab.py). The status line comes from the new `inspect_database()` in [connection.py](../../src/iqdm/db/connection.py), which opens the file read-only. The check runs in the `TaskRunner` when the tab opens, after Browse, when the path field loses focus and on "Check connection". |
| NAS roots and display offset | Done | Add, Edit and Remove for `nas_roots`. A wrong root is shown in the error colour, with a tooltip and an error line. The offset spin box runs from −12 to 14 h in steps of 0.25, with a preview. |
| applying changes without a restart | Done | [app.py](../../src/iqdm/app.py) asks before a Save that would clear Log tab input, then passes the new configuration to `LogTab.apply_config()` in [log_tab.py](../../src/iqdm/gui/log_tab.py) (D33). The status bar follows. A configuration error opens the app on the Settings tab. |
| tests | Done | 101 new tests, all under `tmp_path`. See the table below. |

| File | Tests | Covers |
| --- | --- | --- |
| [test_config.py](../../tests/test_config.py) | 40 more (79) | `read_config_data`, `settings_from_data`, `settings_errors`, `hidden_key_error`, `merge_settings`, `save_config`: missing folder, read back with UNC and non-ASCII paths, comments lost, first and later backups, leftover `.new` file, wrong value, failed rename, failed serialising, unreadable old file |
| [test_connection.py](../../tests/test_connection.py) | 8 more (33) | `inspect_database` for current, newer, older, foreign, non-database, missing and folder paths; the file stays byte-identical |
| [test_settings_tab.py](../../tests/test_settings_tab.py) | 36 (new) | Status line texts and offset preview; loading; no configuration path; checks on demand, on focus loss and after Browse; late check results dropped; NAS roots; offset range and steps; Save, keys kept, backup, answer No, failed write; wrong hidden key; unreadable file; Reload; `--db` and `--config` notes; Open folder; version; error colours in a light and a dark palette |
| [test_log_tab.py](../../tests/test_log_tab.py) | 8 more (66) | New offset in new-entry and edit mode keeps the form; new database clears the form and loads its lists; database path removed; new NAS roots; lists from the old database dropped; `has_unsaved_input()` |
| [test_app_smoke.py](../../tests/test_app_smoke.py) | 9 more (21) | Four tabs; `config_path_for`; a bad configuration opens on the Settings tab; Save applies to the Log tab and the status bar; `--db` stays in force; Yes and No for unsaved Log tab input; no question for an offset change; no Save while the Log tab saves |

## Decisions made

The user chose the proposed default for every open item and for both questions found
while planning, on 2026-10-02:

- D31, writing `config.toml` with `tomli-w` (closes O18).
- D32, name of the Settings milestone (closes O27).
- D33, applying settings without a restart (closes O28). The plan refined the default:
  only a new `db_path` or new NAS roots clear the Log tab form, and only those ask.
- D34, keys in the Settings tab (closes O30).
- D35, backup of `config.toml` (closes O31).
- D36, a wrong value in a key the Settings tab does not show: Save stays disabled.
- D37, status line for an older database: "cannot read or write".

The user also approved the new branch and the new dependency, `tomli-w==1.2.0`.

## Changes from the plan

- **One code commit more than the plan.** `a7e647f` changes the message for a wrong
  NAS root, found in the screenshots (issue 1).
- **"Reload from file" button.** The plan did not name it. D36 needs it after a key is
  corrected by hand, and it also drops changes that are not saved.
- **Save is disabled while nothing has changed.** The plan listed this among the tests.
  A file that cannot be read, or that `load_config()` refuses, can be saved without a
  change.
- **Lists still loading from the old database are dropped.** `LogTab.reload_choices()`
  now ignores a result that a later reload replaced. Without this, a slow reply from
  the old database could fill the site list after a change of `db_path`.
- **No Save while the Log tab saves.** The plan did not cover a save in progress. The
  app shows a message and writes nothing.
- **`NO_DATABASE` text.** The Log tab and status bar now point to the Settings tab.

## Not done in this milestone

| Item | Where it lands |
| --- | --- |
| "Upgrade database" button | O19, with the first real schema migration (D30) |
| Keys for later milestones in the tab | Milestones 4, 5 and 6 (D34) |
| A warning when the user leaves the tab with changes that are not saved | Not planned. The changes stay in the fields until Save or Reload. |
| Rebuilding the PyInstaller onedir build with `tomli-w` | Milestone 7, or on request |

## Untested or not testable here

- **A database on the NAS.** Agents may not access network paths. The check opens a
  read-only connection in the worker, so a slow share should keep the window
  responsive. The user can check this with a scratch database on the NAS (O21).
- **"Open folder" in Explorer.** The tests replace the opener with a stub. The manual
  test set covers it.
- **Disabled buttons by eye.** The offscreen style draws enabled and disabled buttons
  nearly alike, so the screenshots do not show the state of Save. The tests check it.
- **The packaged build.** `tomli-w` is pure Python and imported in the usual way, so
  PyInstaller should collect it. No build was made.
- **Windows dark mode by hand.** The screenshots used a light and a dark palette
  offscreen. Both were readable, and the error colour follows the theme.

## Issues found in self-review

1. **Doubled backslashes in the NAS root message.** The screenshots showed
   `nas_roots entry 'D:\\data' is not a UNC path`, because the message used `repr()`.
   Fixed in `a7e647f`. The same message appears in the status bar at startup.
2. **The status line checks the path in the field.** With `--db`, the run uses the
   `--db` path, but the status line checks the database path in the field. The note
   under the field names the `--db` path. Left unchanged.
3. **Foreign keys and busy timeout describe the app's connection.** The status line
   shows them as SPEC section 4 asks. They are always "on" and 5000 ms, because the app
   sets them on every connection. Only the journal mode describes the file. Left
   unchanged.
4. **Wrong dates in the documentation.** STATUS.md, D27 to D30 and the Milestone 3
   report give 2026-10-03 for the Milestone 3 merge and the Settings decisions. The
   commits (`ce48c2c` to `77ed32c`) are dated 2026-10-02, UTC+8. The new entries D31
   to D37 use 2026-10-02. The old dates are unchanged. Should they be corrected?
5. **STATUS.md said that the hook change was not committed.** Commit `77ed32c`
   committed it. STATUS.md is corrected in this milestone's documentation commit.
6. **A value of the wrong type in a shown key shows the default.** For example,
   `db_path = 7` shows an empty field, and `display_utc_offset_hours = "5"` shows 8.00.
   The error line names the problem, and Save writes the value shown. Left unchanged.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| Run the manual test set below | User | Only a person can judge the tab and the questions it asks |
| Decide issue 4 | User | Dates in four documents |
| Optional: check a database on the NAS from the Settings tab | User | Network paths are not testable here |

### Manual test set

The agent created the files in `dev/m3a-manual/` with `setup.py` in that folder:
`config.toml` (with a comment, an unknown key `colour` and `storage_roots`),
`bad.toml` (not valid TOML), `hidden.toml` (`network_speed_mb_s = -1`), `current.db`
and `second.db` (one site each), `newer.db` (`user_version` 3), `other.db` (a SQLite
file without the app's tables) and `notadb.db` (text).

Start the app in the activated venv. `--config` keeps your real `%APPDATA%` file
unchanged:

```
python -m iqdm --config dev/m3a-manual/config.toml
```

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Open the Settings tab. | Database path `...\current.db`, root `\\nas\recordings`, offset 8.00 h. Status: "File found. Schema version 1, current. Journal mode delete, foreign keys on, busy timeout 5000 ms." Save disabled. About names `config.toml` and says "Started with --config". |
| 2 | Browse to `newer.db`, then `other.db`, then `notadb.db`. Type `absent.db` and press Tab. | "Schema version 3, too new ..."; "Not an IQ Data Manager database (schema version 0)"; "Cannot read the file as an SQLite database ..."; "The file was not found." Click "Reload from file" afterwards. |
| 3 | Set the offset to 5.5. Then type 5.1. | Preview "2026-09-30 07:30:00 (UTC+5:30)". With 5.1, a red line about steps of 0.25 and Save disabled. |
| 4 | Set the offset to 0 and Save. Open the Log tab. | No question. Labels read "Start (UTC)" and "End (UTC)". |
| 5 | Add root `D:\data`. | The entry turns red. A line reads "nas_roots entry 'D:\data' is not a UNC path". Save disabled. Edit it to `\\nas2\iq`: Save enabled. Do not save yet. |
| 6 | In the Log tab, type remarks. In the Settings tab, Browse to `second.db` and Save. | A question about clearing the Log tab form. Answer No: nothing is written (`config.toml` unchanged in an editor). |
| 7 | Save again and answer Yes. | The Log tab form is empty. Its site list shows "Site in second.db". The status bar names `second.db`. |
| 8 | Open `config.toml` and `config.toml.bak` in an editor. | The comment is gone. `colour` and `storage_roots` are still there. The roots are `\\nas\recordings` and `\\nas2\iq`. The `.bak` file holds the file as it was before step 7. |
| 9 | Click "Open folder". | Explorer opens `dev\m3a-manual`. |
| 10 | Quit. Start with `--config dev/m3a-manual/bad.toml`. | The app opens on the Settings tab. A red line says that the file cannot be read. Save is enabled. Save: `bad.toml` is valid, and `bad.toml.bak` holds `db_path = `. |
| 11 | Quit. Start with `--config dev/m3a-manual/hidden.toml`. | A red line names `network_speed_mb_s`. Save stays disabled after any change. Set the value to 50 in an editor and click "Reload from file": the line goes. |
| 12 | Quit. Start with `--config dev/m3a-manual/config.toml --db dev/m3a-manual/current.db`. Change the path to `second.db` and Save. | Both "Started with --db" notes appear. After Save, the status bar still names `current.db`, and the Log tab keeps its form. |
| 13 | Repeat steps 1 and 5 in Windows light mode. | All text readable. Red marks readable. |

## Build output and files for the user to remove

- `dev/m3a-shots/`: the screenshot script, `shot.db`, `config.toml` and two PNG files.
- `dev/m3a-manual/`: the manual test set. Remove it after the manual tests.

Both folders are under `dev/`, which `.gitignore` excludes.

## Recommendation and question

Run the manual test set, then merge `m3a-settings` into `main` as a fast-forward. Does
the user approve the merge after the manual tests? Should the dates in issue 4 be
corrected?
