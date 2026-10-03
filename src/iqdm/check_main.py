"""Console program IQDataManager-check.exe (DECISIONS.md D57).

The recording laptops have no Python, and the windowed IQDataManager.exe has no
console for printed output. This program runs the diagnostics of the NAS field test
(D54) in a console window, from the same build folder:

    IQDataManager-check.exe copy-check DEST_DIR --source DIR [options]
    IQDataManager-check.exe db-check create|check|hold|write PATH [--seconds N]
    IQDataManager-check.exe make-test-set OUT_DIR [--quick] [options]
    IQDataManager-check.exe COMMAND --help

Each command is the matching module in iqdm.diagnostics; tools/ runs the same code.
Exit codes are those of the command; 2 for a usage error.
"""

import sys
from collections.abc import Callable

from iqdm import __version__
from iqdm.diagnostics import copy_check, db_check, testset

PROG = "IQDataManager-check.exe"
Command = Callable[[list[str], str], int]
COMMANDS: dict[str, tuple[Command, str]] = {
    "copy-check": (
        lambda argv, prog: copy_check.main(argv, prog),
        "copy a folder with 1, 4 and 8 files at once, flush on and off, and time it",
    ),
    "db-check": (
        lambda argv, prog: db_check.main(argv, prog),
        "create a scratch database, or check opening, writing and locking",
    ),
    "make-test-set": (
        lambda argv, prog: testset.main(argv, prog),
        "write the synthetic recordings of the NAS field test",
    ),
}


def usage() -> str:
    lines = [f"usage: {PROG} COMMAND [options]", "", "commands:"]
    lines += [f"  {name:<14} {text}" for name, (_, text) in COMMANDS.items()]
    lines += ["", f"Run {PROG} COMMAND --help for the options of a command."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run one command. Returns its exit code."""
    args = sys.argv[1:] if argv is None else list(argv)
    if not args or args[0] in ("-h", "--help"):
        print(usage())
        return 0 if args else 2
    if args[0] == "--version":
        print(f"{PROG} {__version__}")
        return 0
    found = COMMANDS.get(args[0])
    if found is None:
        print(f"{PROG}: unknown command {args[0]!r}\n\n{usage()}", file=sys.stderr)
        return 2
    command, _ = found
    try:
        return command(args[1:], f"{PROG} {args[0]}")
    except SystemExit as exc:  # argparse ends --help and usage errors this way
        return exc.code if isinstance(exc.code, int) else 2


if __name__ == "__main__":
    sys.exit(main())
