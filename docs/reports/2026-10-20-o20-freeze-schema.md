# Version 1 schema frozen (open item O20)

| | |
| --- | --- |
| Branch | `o20-freeze-schema-v1` |
| Commits | `a5e121a` (PLAN.md, the approved plan for version 1.1), plus the commit of this work and report |
| Tests | 1,610 passed, 4 skipped (`pytest`), `ruff check` clean |
| Report date | 2026-10-20 |
| Merge status | Not merged |

## Objectives against what was delivered

O20 in `docs/STATUS.md` read: "Frozen copy of the version 1 schema for testing future
migrations. The real catalogue will be made with the 1.0.0 build, so the schema at
`v1.0.0` is version 1." Its proposed default was: "Copy `schema.sql` of `v1.0.0` to
`tests/schemas/v1.sql`. A test builds a database from it, applies
`migrations.upgrade()`, and compares its tables and columns with a database built from
the current `schema.sql`. From then on, `schema.sql` changes only together with a
migration."

| Objective | Status | Notes |
| --- | --- | --- |
| Copy `schema.sql` of `v1.0.0` to `tests/schemas/v1.sql` | Done | [v1.sql](../../tests/schemas/v1.sql). Its SHA-256 with LF line endings, `0416405082f3760c120afdf6c4682fa5844ddaa957f6e273942ebea431d63ff2`, equals that of `git show v1.0.0:src/iqdm/db/schema.sql`. A test checks it. |
| A test builds a database from it, applies `migrations.upgrade()`, and compares it with the current schema | Done | `test_a_version_1_database_upgraded_has_the_current_structure` in [test_schema_freeze.py](../../tests/test_schema_freeze.py). It compares tables with their columns (type, not null, default, primary key), indexes with their columns, and triggers by name and table. |
| `schema.sql` changes only together with a migration | Done | `test_schema_sql_is_not_edited_in_place_while_the_version_is_1` requires the same statements in `sqlite_master` from both files while `LATEST_VERSION` is 1. It skips after the first migration, when the upgrade test takes over. |

The pilot passed (user, 2026-10-20), so the real catalogue exists and was made with
the 1.0.0 build. Its schema is the one in `v1.sql`.

## Decisions made

D77, "Version 1 schema frozen".

## Changes from the plan

- PLAN.md said the in-place test compares the two files "apart from line endings".
  The test compares the statements that the files build in `sqlite_master`. Comments
  outside the statements may therefore change. This allowed the header comment of
  `schema.sql` to say that version 1 is frozen. The frozen copy itself cannot change,
  because its SHA-256 is checked.
- Comments that still said `schema.sql` is edited in place were updated:
  [schema.sql](../../src/iqdm/db/schema.sql) lines 2 and 3, the docstrings of
  [migrations.py](../../src/iqdm/db/migrations.py) and
  [version.py](../../src/iqdm/db/version.py), and README "Run". No statement changed.
- The error text in `migrations.upgrade()` for a file that lacks part of
  `schema.sql` still says that `schema.sql` was edited in place before the first real
  database. That text describes databases made before 1.0.0 and stays correct, so it
  was left alone.

## Other records in this commit

- STATUS.md:
  - O20 closed by D77.
  - O42 closed on the user's word ("no issue").
  - O43, O44 and O45 added as the user approved them. O41 moved to 1.1.0 with O45.
  - The next free number is O46.
  - The pending checks of D75 on the NAS and D76 across two PCs closed on the user's
    report that the pilot passed.
  - A new table, "Work after 1.0".
- HANDOFF.md: section 5 states the freeze. Section 3 names the next numbers. Section 6
  says what changed since the handoff.
- SPEC.md section 3: version 1 is frozen, and a change comes with a migration.
- DECISIONS.md: D77, and D4's status says D77 ends the edits in place.

## Not done in this piece of work

| Item | Where it lands |
| --- | --- |
| "Upgrade database" in the Settings tab | O19, with the first real migration |
| CHECK constraints and trigger text in the upgrade comparison | The test of the migration that changes them (D77) |

## Untested or not testable here

- Nothing in this work touches the real catalogue. The tests build their databases
  under `tmp_path`.
- The upgrade test runs `upgrade()` at version 1, where no step exists. It shows the
  frozen schema and the current one agree. It cannot yet show a real migration
  working. The first migration exercises it.

## Issues found in self-review

1. **The D76 check across two PCs is closed on an inferred answer.** The user
   answered "Pilot done, all passed" to a question that listed D76 across two PCs
   with the pilot checks. STATUS.md says so, and the user was asked to say if D76
   across two PCs was not tested.
2. **`docs/KICKOFF.md` has a change in the working tree that this work did not
   make.** It looks like the user's session prompt. It was not staged or committed.

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| `pytest` and `ruff check` | Agent | 1,610 passed, 4 skipped; clean |
| Confirm D76 across two PCs passed in the pilot | User | STATUS.md closes it on that reading |

## Build output and files for the user to remove

None.

## Recommendation and question

Merge `o20-freeze-schema-v1` into `main` as a fast-forward? The next branch,
`viewer-multi-filter` (O38), can start from `main` after the merge, or from this
branch if the merge waits.
