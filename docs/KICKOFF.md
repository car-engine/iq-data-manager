# Starting the first Claude Code session

## Before the session (do these yourself)

1. **Create the repo.** Unzip this starter bundle into `iq-data-manager/`, open the
   folder in VS Code, then in a terminal:

   ```
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   git init
   git add .
   git commit -m "Starter: spec, schema, CLAUDE.md, safety config"
   ```

   Push to a private GitHub/GitLab repo so a remote backup exists from the start.

2. **Cut off real data.** Disconnect the NAS mapped drive on this PC (or sign in with a
   read-only account) for the duration of Claude Code sessions. Keep the real master
   `.db` out of the repo folder.

3. **Install Claude Code** following the official instructions at
   https://code.claude.com/docs. Git for Windows (already installed) provides the
   shell it uses.

4. **Optional, machine-wide:** copy the `permissions.deny` list from
   `.claude/settings.json` into your user settings file
   (`%USERPROFILE%\.claude\settings.json`) so the same deny rules apply in every
   project on this PC, not just this repo.

## Verify the guards (first 2 minutes of the session)

Start Claude Code from the repo root, then:

1. Run `/permissions` and check the deny rules from `.claude/settings.json` are listed.
2. Run `/hooks` and check the `PreToolUse` hook is registered.
3. Create a throwaway folder yourself in Explorer (e.g. `scratch_test`), then ask:
   "Run `rm -rf scratch_test` in the shell." Expect it to be refused by a deny rule
   or the hook, and the folder to still exist.
4. Ask: "Run `python -c \"import shutil; shutil.rmtree('scratch_test')\"`." Expect the
   hook to block it (this is the case deny rules alone miss).
5. Delete `scratch_test` yourself.

If either test is not blocked, stop and fix the configuration before any development.
Common causes: `python` not on PATH for the hook (use the full path to python.exe in
`settings.json`), or rule syntax changes in a newer Claude Code version (check the
settings docs).

## Session habits

- Stay in the default permission mode. Never use `--dangerously-skip-permissions` or
  bypass mode in this repo.
- Use plan mode (Shift+Tab) at the start of each milestone and review the plan.
- Read each command before approving it.
- Commit after each working step; `git diff` before approving large edits.
- Do not run Claude Code from an Administrator terminal.

## Kickoff prompt (paste as the first message, in plan mode)

```
We're starting a new project. Read CLAUDE.md and docs/SPEC.md in full, and the schema
at src/iqdm/db/schema.sql. The safety rules in CLAUDE.md are non-negotiable.

Then:

1. Summarise your understanding of the app in a few paragraphs, and list anything in
   the spec that is ambiguous, contradictory, or that you'd push back on. Ask me about
   those before writing code.
2. Propose a detailed plan for Milestone 0 (Scaffold) only: files you'll create,
   dependencies with pinned versions, pyproject/ruff/pytest configuration, what
   tools/make_fixtures.py will do, and how you'll confirm the PyInstaller smoke build.

Do not write any code until I've approved the plan. Work only inside this repository.
```

## Later milestones

Start each milestone with a short prompt in plan mode, for example:

```
Milestone 1 (Database layer) from docs/SPEC.md. Re-read sections 3 and 9 and
CLAUDE.md, then propose a plan with the test list before implementing.
```

For milestones 5 and 6 (anything that copies or deletes files), also ask Claude to list
every code path that can delete or overwrite a file, and review that list yourself.

## Resuming in a new session

A new session has no memory of earlier ones. Everything it needs is in the repository.
Paste this in plan mode, with the milestone filled in:

```
Read CLAUDE.md, docs/STATUS.md and the latest milestone report that STATUS.md links
to. Then read the docs/SPEC.md sections for Milestone <n> and the DECISIONS.md
entries they refer to. Summarise the current state and the open items in STATUS.md that belong
to Milestone <n>, then propose a plan for Milestone <n> with its test list. Ask me
about the open items before writing code.
```

At the end of the milestone, Claude writes a report in `docs/reports/` that follows
`docs/REPORT_TEMPLATE.md` and updates `docs/STATUS.md`.

## Release review

Before version 1.0, a fresh session reviews the whole repository, reports, and then
fixes what the user approves. Paste this in plan mode:

```
Review IQ Data Manager before release 1.0, then fix what I approve. The work is on
branch m8-release, which is not merged into main. Stay on that branch.

Read first: CLAUDE.md, docs/STATUS.md (including "Notes for agents"), docs/SPEC.md,
docs/DECISIONS.md (D1 to D74; D65 to D74 are the newest), docs/USER_GUIDE.md,
README.md, and docs/reports/M5.md, M6.md, M7.md and M8.md. M8.md is part 1 of the
current milestone's report.

Phase 1 is a review only. Do not change code, tests or documents, and do not commit
fixes. Write your findings to docs/reports/<YYYY-MM-DD>-release-review.md, keep
numbers exact and name files as links, as docs/REPORT_TEMPLATE.md asks, and commit
only that file.

Steps:
1. Run pytest and ruff check. Record the counts.
2. Build into new folders, dist/review-1 and build/work-review-1, with the commands in
   README.md, "Build". Run the smoke test and the longPathAware check there.
3. Review the code against SPEC.md and the decisions, most important first:
   a. Data safety. Every path that deletes, overwrites, renames or creates a file:
      the tables "Code paths that delete or overwrite a file" in M6.md and "Code that
      creates or overwrites a file" in M7.md. Confirm that transfer/delete.py is the
      only module that deletes, that its conditions match SPEC.md section 8
      "Transfer safety" and D52, D55 and D74, and that no path replaces an existing
      file.
   b. The database: schema.sql, db/version.py (the D73 check of a file against
      schema.sql, which runs on every connection), db/repository.py, migrations, and
      the connection rules in CLAUDE.md.
   c. Transfers: copier, verify, selection, pathcheck and operations, including stop,
      resume (D51, D63) and Check archive (D71).
   d. The GUI: the four tabs; work that can take more than about 100 ms runs off the
      Qt main thread; the unsaved-settings question (D70); the project (D73).
   e. The legacy import (D66, D71) and the console program IQDataManager-check.exe.
   f. Packaging: build/iqdm.spec, the defaults file (D68), and the files written
      next to the programs.
4. Check the documents against the code and against each other. SPEC.md must state
   the current requirement of every active decision. USER_GUIDE.md must match the
   labels and behaviour on screen. README.md commands must work. STATUS.md must be
   current. Report each contradiction.
5. Check the visible text against CLAUDE.md, "User-facing text".
6. Where it helps, render the tabs offscreen in light and dark palettes under
   dev/review/, as "Notes for agents" in STATUS.md describes.

For each finding give: a severity (blocker for 1.0, should fix, or minor), the file
and line, what is wrong, a concrete failure (input or state, and the wrong result),
and how you confirmed it (the test you ran or the code you read). Report only what
you confirmed. List suspicions separately as unconfirmed. Also list what you could
not check, such as the NAS and real data, and anything a new maintainer would miss
in the documents.

Known, and not findings: the open items in STATUS.md (O19, O20, O22, O37); the
version is still 0.1.0, which a release step changes; the user has not yet tried
D73 by eye.

The safety rules in CLAUDE.md apply in full. Never use network paths, real
databases, delete commands or robocopy. Git commands are limited to status, diff,
log, add and commit. The safety hook blocks any shell command that contains a UNC
path; do not run such commands and do not look for a workaround, but report what
was blocked. Write files only with the Write and Edit tools.

At the end of phase 1, give in chat: the test and lint counts, the blockers, and
your recommendation on releasing 1.0.

Phase 2 fixes the findings. Propose a plan: which findings to fix, how, and the
tests for each. Wait for my approval. Then implement the approved fixes on
m8-release in small commits, run pytest and ruff check, record any new decision in
DECISIONS.md and SPEC.md, add "Part 2" to docs/reports/M8.md, and update
docs/STATUS.md. Do not merge or push without my approval.
```
