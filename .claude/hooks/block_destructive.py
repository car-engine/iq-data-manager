"""Claude Code PreToolUse hook: block destructive or out-of-bounds tool calls.

Claude Code sends the pending tool call as JSON on stdin. Exiting with code 2
blocks the call and shows the stderr message to Claude. Exit code 0 allows it.

This is a second layer on top of the deny rules in .claude/settings.json. Those
rules match command prefixes; this script inspects the whole command text, so it
also catches deletions inside chained commands, python -c one-liners and aliases.

Standard library only. Runs with whatever `python` is on PATH.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Command-position prefix: start of command, or after ; & | ( or `cmd /c`.
_CMD_START = r"(?:^|[;&|(]\s*|\bcmd(?:\.exe)?\s+/c\s+)"

BLOCKED_COMMAND_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\b", "rm (delete)"),
    (r"\brmdir\b", "rmdir (delete directory)"),
    (_CMD_START + r"(?:del|erase|rd)\b", "del/erase/rd (delete)"),
    (_CMD_START + r"ri\s", "ri (Remove-Item alias)"),
    (r"remove-item", "Remove-Item (delete)"),
    (r"clear-content", "Clear-Content (erase file contents)"),
    (r"rimraf", "rimraf (delete)"),
    (r"rmtree", "shutil.rmtree (delete)"),
    (r"\bos\.(?:remove|unlink|removedirs)\b", "os.remove/unlink (delete)"),
    (r"\.unlink\s*\(", "Path.unlink (delete)"),
    (r"\.rmdir\s*\(", "Path.rmdir (delete)"),
    (r"send2trash", "send2trash (delete)"),
    (r"\brobocopy\b", "robocopy (transfer scripts are run by the user only)"),
    (r"\bformat(?:\.com)?\s+[a-z]:", "format (disk)"),
    (r"\bdiskpart\b", "diskpart (disk)"),
    (r"\bcipher\s+/w", "cipher /w (wipe)"),
    (r"\bnet\s+use\b", "net use (network drive mapping)"),
    (r"\bgit\s+push\b.*(?:--force|\s-f\b|--force-with-lease)", "git force push"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
    (r"\bgit\s+clean\b", "git clean"),
    (r"\bgit\s+rebase\b", "git rebase"),
    (r"\bshutdown\b", "shutdown"),
]

# UNC paths (\\server\share) and //server/share forms in shell commands.
UNC_PATTERNS = [
    r"(?:^|[\s\"'=(,;|&<>`])\\{2}(?:\\{2})?[A-Za-z0-9_.\-]+\\",
    r"(?<![:A-Za-z])//\d{1,3}(?:\.\d{1,3}){3}/",
]

FILE_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
PROTECTED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".db-journal"}


def block(reason: str) -> None:
    print(
        f"BLOCKED by project safety hook: {reason}. "
        "Do not try to work around this. Tell the user what was blocked and ask "
        "how to proceed.",
        file=sys.stderr,
    )
    sys.exit(2)


def check_command(command: str) -> None:
    text = command.lower()
    for pattern, label in BLOCKED_COMMAND_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            block(f"command contains {label}")
    for pattern in UNC_PATTERNS:
        if re.search(pattern, command):
            block("command references a network (UNC) path")


def check_file_write(file_path: str, project_dir: Path) -> None:
    if file_path.startswith("\\\\") or file_path.startswith("//"):
        block(f"write to a network path: {file_path}")
    target = Path(file_path)
    if not target.is_absolute():
        target = project_dir / target
    try:
        resolved = target.resolve()
    except OSError:
        block(f"could not resolve path: {file_path}")
        return
    project = project_dir.resolve()
    if resolved != project and project not in resolved.parents:
        block(f"write outside the project folder: {file_path}")
    if (project / ".claude") == resolved or (project / ".claude") in resolved.parents:
        block("edits to .claude/ (safety configuration) are not allowed")
    if resolved.suffix.lower() in PROTECTED_SUFFIXES:
        block(f"writes to database files are not allowed: {file_path}")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        block("hook could not parse the tool call (failing closed)")
        return

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    project_dir = Path(
        os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    )

    command = tool_input.get("command")
    if isinstance(command, str):
        check_command(command)

    if tool_name in FILE_WRITE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if isinstance(path, str):
            check_file_write(path, project_dir)

    sys.exit(0)


if __name__ == "__main__":
    main()
