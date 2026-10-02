# Report template

Use this format at the end of every milestone, and after any other significant piece
of work. A milestone report goes in `docs/reports/M<n>.md`. A report for other work
goes in `docs/reports/<YYYY-MM-DD>-<topic>.md`. Give the same summary in chat, then
update `docs/STATUS.md`.

The report is for two readers: the project owner, who decides whether to merge, and
a future agent starting with no memory of the session. Each section must make sense
without the conversation that produced it.

Rules:

- Quote the milestone objectives from `docs/SPEC.md` section 12 word for word, then
  judge each one. Do not reword the objective to fit what was delivered.
- Status values: **Done**, **Done, with gaps** (say which gaps), **Partly done**,
  **Not done**, **Deferred** (say to which milestone).
- Keep every number exact: test counts, commit hashes, file sizes, timings.
- Say what was not tested and why. "Tested locally only" is a valid status.
- Name files as relative links, for example `[connection.py](../../src/iqdm/db/connection.py)`.
- Report issues found in self-review. Do not fix them silently, and do not fix
  anything outside the agreed scope.
- Follow the writing rules that apply to the session (plain technical prose, British
  spelling).

---

## Template

```markdown
# Milestone <n>: <name>

| | |
| --- | --- |
| Branch | `<branch>` |
| Commits | `<first>` to `<last>` (<count> commits) |
| Tests | <N> passed (`pytest`), `ruff check` clean |
| Report date | <YYYY-MM-DD> |
| Merge status | <not merged / merged into main as <hash>> |

## Objectives against what was delivered

SPEC section 12 defines this milestone as: "<objective text, quoted>".

| Objective | Status | Notes |
| --- | --- | --- |
| <objective 1> | Done | <what exists, where, how it is tested> |
| <objective 2> | Done, with gaps | <which gaps and why> |

<Optional supporting tables, for example operations per table or features per tab.>

## Decisions made

<New DECISIONS.md entries (numbers and titles), or "None".>

## Changes from the plan

<Each deviation from the approved plan and why, or "None".>

## Not done in this milestone

| Item | Where it lands |
| --- | --- |
| <item> | Milestone <n> / user / open question O<n> |

## Untested or not testable here

<Things the agent cannot test: network paths, real data, real SMB locking, GUI by
eye. Say who can test each and how.>

## Issues found in self-review

1. **<short title>.** <what is wrong or risky, and what was done about it: fixed,
   left unchanged, or added to STATUS as O<n>.>

## Checks before merging

| Check | Who | Why |
| --- | --- | --- |
| <check> | Agent / user | <what it proves> |

## Build output and files for the user to remove

<Paths the agent created and cannot delete, or "None".>

## Recommendation and question

<The recommended next step, then the decision the user needs to make, for example
"Merge m1-database into main (fast-forward)?">
```
