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

For milestones 5 and 6 (anything that moves or deletes files), also ask Claude to list
every code path that can delete or overwrite a file, and review that list yourself.

## Resuming in a new session

A new session has no memory of earlier ones. Everything it needs is in the repository.
Paste this in plan mode, with the milestone filled in:

```
Read CLAUDE.md, docs/STATUS.md and the latest report in docs/reports/. Then read
the docs/SPEC.md sections for Milestone <n> and the DECISIONS.md entries they
refer to. Summarise the current state and the open items in STATUS.md that belong
to Milestone <n>, then propose a plan for Milestone <n> with its test list. Ask me
about the open items before writing code.
```

At the end of the milestone, Claude writes a report in `docs/reports/` that follows
`docs/REPORT_TEMPLATE.md` and updates `docs/STATUS.md`.
