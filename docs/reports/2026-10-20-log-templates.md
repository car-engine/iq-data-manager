# Log tab templates (open item O44)

| | |
| --- | --- |
| Branch | `log-templates`, from `log-keep-fields` at `2b49761` |
| Commits | The commit of this work and report |
| Tests | 1,678 passed, 4 skipped (`pytest`), `ruff check` clean |
| Report date | 2026-10-20 |
| Merge status | Not merged. Merge after `log-keep-fields`, as fast-forwards in order. |

## Objectives against what was delivered

O44 in `docs/STATUS.md` read: "Import and export a Log tab template file, for example
for common hardware set-ups". Its proposed default, as the user corrected it on
2026-10-20 and approved, was: "A TOML file that can hold every field the user types:
logged by, site, project, plan reference, remarks, sample type, IQ layout, endianness,
header bytes, band and fc per channel number, and the RF chain rows. Values that come
from the scan are never in it. Every field is optional. Export asks which fields to
save. Import changes only the fields the file holds. A site or project name the
catalogue does not hold is not added; the message line names it."

| Objective | Status | Notes |
| --- | --- | --- |
| A TOML file that can hold every typed field | Done | [templates.py](../../src/iqdm/templates.py): `LogTemplate`, `to_toml_data`, `from_toml_data`, `read_template`, `write_template`. `test_round_trip_through_a_file`, `test_export_then_import_gives_the_same_form`. |
| Never a value from the scan | Done | `test_a_template_holds_the_typed_fields_and_nothing_from_the_scan`; after an import, fs still comes from the scan (`test_export_then_import_gives_the_same_form`). |
| Every field optional | Done | `test_each_field_alone` (one test per field group), `test_numbers_are_read_as_text`. |
| Export asks which fields to save | Done | [template_fields.py](../../src/iqdm/gui/widgets/template_fields.py), `TemplateFieldsDialog`: one tick box per group with the current value or a count; empty fields start unticked; Save needs a ticked box. `test_the_export_dialog_starts_with_empty_fields_unticked`, `test_only_the_chosen_fields_are_written`. |
| Import changes only the fields the file holds | Done | `apply_template`. `test_import_changes_only_the_fields_the_template_holds`, `test_export_of_some_fields_imports_only_those`, `test_import_before_a_scan_fills_the_channels_when_the_scan_ends`. |
| A missing site or project is named and not added | Done | `test_a_name_the_catalogue_lacks_is_named_and_changes_nothing`, `test_import_names_a_site_the_catalogue_lacks`. |

## Decisions made

D80, "Log tab templates in files".

## Changes from the plan

- **The last folder used** is remembered for the session only. The plan said
  `QSettings`. No code in the app uses `QSettings`, and on Windows it writes to the
  registry, also when the tests run. That would break the rule that no test writes
  outside its temp folder.
- **The replace question.** The file dialog opens with Qt's own overwrite question
  switched off. The tab asks once, defaulting to No, after it has added `.toml` to
  the name. Otherwise a name typed without `.toml` could replace a file without a
  question.
- **Unknown entries are errors.** A misspelt key, such as `sampletype`, would
  otherwise be ignored without a word. The version is checked first, so another TOML
  file, such as `config.toml`, gives "not a template from this program" and its keys
  are not listed.
- An RF chain list that is present but empty clears the form's rows. A file without
  the list leaves them.

## Code that creates or overwrites a file

| Code | What it writes | Guard |
| --- | --- | --- |
| `templates.write_template()`, `new_path.write_text()` then `new_path.replace(path)` | `<name>.toml.new`, then the template file the user chose | The text is read back and compared before anything is written. `LogTab.export_template()` asks before it replaces an existing file, defaulting to No (`test_export_asks_before_it_replaces_a_template`). It writes only to a path the user chose in the file dialog. A failure before the rename leaves an existing template unchanged. |

No `.unlink()`, `.rmdir()` or `shutil` call was added. `templates.py` imports no Qt.
The architecture test still passes.

## Not done in this piece of work

| Item | Where it lands |
| --- | --- |
| Adding a missing site or project on import | Left to the user (question 2 of the plan); the default is not to add |

## Untested or not testable here

- The real file dialogs were not opened; the tests pass paths and fields directly, or
  replace `QFileDialog.getSaveFileName`. The dialog for the fields was rendered
  offscreen in the light and a dark palette (`dev/o44-shots/`).
- Templates in a shared folder on the NAS: not tested, because agents use no network
  path. Reading and writing go through the same `Path` calls as a local file.

## Issues found in self-review

1. **`log_tab.py` is not in `ruff format` style** on `main`. Only `ruff check` is the
   gate (STATUS.md, "Notes for agents"), so the new code follows the file's existing
   style and the file was not reformatted.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 1,678 passed, 4 skipped; clean |
| Export a template for a real set-up, import it into a new entry, in the 1.1 build | User | The dialogs on a real display and the template's use in practice |

## Build output and files for the user to remove

`dev/o44-shots/`: the screenshot script, four screenshots and two scratch databases.
Listed in STATUS.md.

## Recommendation and question

Merge after `log-keep-fields`. The next branch, `transfer-queue` (O45 with O41),
starts from this one. Should a site or project named in a template, and missing from
the catalogue, be added on import? The default is no.
