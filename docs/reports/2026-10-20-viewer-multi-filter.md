# Viewer filters with several choices (open item O38)

| | |
| --- | --- |
| Branch | `viewer-multi-filter`, from `o20-freeze-schema-v1` at `fee1198` |
| Commits | The commit of this work and report |
| Tests | 1,621 passed, 4 skipped (`pytest`), `ruff check` clean |
| Report date | 2026-10-20 |
| Merge status | Not merged. Merge after `o20-freeze-schema-v1`, as fast-forwards in order. |

## Objectives against what was delivered

O38 in `docs/STATUS.md` read: "Viewer filters on site, project and band take several
choices at once, as a checklist". Its proposed default, approved with the plan for
version 1.1, was: "A drop-down list with a checkbox per entry; nothing ticked means
all. Project lists "No project" as one entry, so it combines with projects. Several
choices of one filter match any of them; different filters must all match, as now.
`RecordingFilter` holds tuples (`site_ids`, `project_ids`, `bands`,
`without_project`), and `_filter_sql()` uses `IN (...)`; band still matches on the
same channel as the frequency range (D43). Amends D43 and the Viewer part of D73."

| Objective | Status | Notes |
| --- | --- | --- |
| A drop-down list with a tick box per entry; nothing ticked means all | Done | [check_combo.py](../../src/iqdm/gui/widgets/check_combo.py), `CheckComboBox`. The closed list shows "All sites" (or projects, bands) or the ticked names; the tooltip lists them. A click ticks an entry and leaves the list open; Space does the same. Tested in [test_check_combo.py](../../tests/test_check_combo.py). |
| "No project" is one entry and combines with projects | Done | [viewer_tab.py](../../src/iqdm/gui/viewer_tab.py) `_fill_choices` and `filter_input`; SQL joins the two with OR. Tested in `test_project_column_filter_and_details` and `test_the_list_names_the_project_and_filters_by_it`. |
| Several choices match any; different filters must all match | Done | `repository._filter_sql()` with `IN (...)`. Tests for sites, projects and bands in [test_repository.py](../../tests/test_repository.py) and [test_viewer_tab.py](../../tests/test_viewer_tab.py). |
| `RecordingFilter` holds tuples | Done | [models.py](../../src/iqdm/models.py). `site_id`, `project_id` and `band` are gone. `parse_filter()` sorts the tuples, removes repeats and drops blank bands. |
| Band matches on the same channel as the frequency range | Done | `test_several_bands_and_the_fc_range_match_on_one_channel`. |
| Amends D43 and the Viewer part of D73 | Done | D78. |

## Decisions made

D78, "Viewer filters with several choices".

## Changes from the plan

- The plan named the widget's text "All sites or a list of the ticked names". The
  tooltip also lists the ticked names, one per line, because a long list is cut off
  in the closed box.
- The project filter of D73 refused a project together with "no project" with a
  `ValueError`. D78 combines them with OR, so the refusal and its test are gone.

## Not done in this piece of work

None.

## Untested or not testable here

- The lists were looked at in offscreen renders with the light palette and a dark
  palette (`dev/o38-shots/`). The look in Windows dark mode by eye is the user's, with
  the 1.1 build.
- A screen reader reads the combo box's current entry, not the summary. Nobody on the
  team was reported to use one.

## Issues found in self-review

1. **Enter in the open list sets the box's current entry.** The box draws its
   summary in place of the current entry, so nothing on screen changes, and the
   filter does not read the current entry. Left as it is.
2. **The mouse wheel over the closed box changes its current entry.** The same
   applies: nothing visible changes. Left as it is.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 1,621 passed, 4 skipped; clean |
| Tick two sites and a project with "No project" in the 1.1 build, in dark mode | User | The look and the click behaviour on a real display |

## Build output and files for the user to remove

`dev/o38-shots/`: the screenshot script, four screenshots and two scratch databases.
Listed in STATUS.md.

## Recommendation and question

Merge `o20-freeze-schema-v1` and then `viewer-multi-filter` into `main` as
fast-forwards? The next branch, `log-keep-fields` (O43), starts from this one.
