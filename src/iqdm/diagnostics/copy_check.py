"""Measure the copy engine's throughput to a folder, for example a scratch folder on the NAS.

DECISIONS.md D48: the app copies files itself. D54: the first measurement on the NAS
runs with the Milestone 6 build, on the test set from make-test-set. The tool copies
one source folder with 1, 4 and 8 files at once, with the flush to the destination's
disks on and off, verifies every copy and prints the times. It uses the app's own copy
engine and verification, so it tests the code the app will run.

The code moved here from tools/copy_check.py, which stays as a wrapper (D57).

Usage, in the packaged app or from the repository:
    IQDataManager-check.exe copy-check DEST_DIR --source DIR [options]
    IQDataManager-check.exe copy-check DEST_DIR --make-source WORK_DIR [--files N]
        [--file-mb MB] [options]
    python tools/copy_check.py DEST_DIR --source DIR [options]
    python tools/copy_check.py DEST_DIR --make-source WORK_DIR [--files N] [--file-mb MB] [options]

Options:
    --workers 1 4 8        files at once, one run each (default 1 4 8)
    --fsync on|off|both    flush each file to the destination's disks (default both)
    --hash                 compute SHA-256 during the copy and compare every file

- DEST_DIR: a new or empty folder at the destination. Each run copies into its own
  subfolder, DEST_DIR/workers-<n>-fsync-<on|off>.
- --source DIR: copy every file under DIR, for example a recording of the test set.
- --make-source WORK_DIR: write N files of random bytes, MB megabytes each
  (10**6 bytes), into WORK_DIR/source on the local disk first.

The tool never deletes anything. Remove DEST_DIR, and WORK_DIR if used, by hand.
Exit codes: 0 every copy verified, 1 a copy failed, 2 usage error.
"""

import argparse
import os
import sys
import time
from pathlib import Path

from iqdm.models import HashMode
from iqdm.transfer.copier import CopyItem, copy_files
from iqdm.transfer.power import keep_awake
from iqdm.transfer.verify import verify_copy

MB = 1_000_000
FIRST_STAMP = 1790733600  # 2026-09-30T02:00:00Z, the fixtures' start time
WRITE_BLOCK = 4 * 1024 * 1024
FSYNC_CHOICES = {"on": (True,), "off": (False,), "both": (True, False)}


class UsageError(Exception):
    """A folder or an argument cannot be used."""


def _new_or_empty(path: Path, label: str) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise UsageError(f"{label} must be a new or empty folder: {path}")


def make_source(work_dir: Path, n_files: int, file_bytes: int) -> Path:
    """Write n_files of random bytes into work_dir/source/0. Returns work_dir/source."""
    folder = work_dir / "source" / "0"
    folder.mkdir(parents=True)
    for i in range(n_files):
        with (folder / f"{FIRST_STAMP + i}.dat").open("xb") as f:
            left = file_bytes
            while left > 0:
                block = min(WRITE_BLOCK, left)
                f.write(os.urandom(block))
                left -= block
    return work_dir / "source"


def list_source(source: Path) -> list[CopyItem]:
    """Every file under source, by '/'-separated relative path."""
    return [
        CopyItem(rel_path=p.relative_to(source).as_posix(), size=p.stat().st_size)
        for p in sorted(source.rglob("*"))
        if p.is_file() and not p.is_symlink()
    ]


def _rate(n_bytes: int, seconds: float) -> str:
    return f"{n_bytes / MB / seconds:8.1f} MB/s" if seconds > 0 else "       - MB/s"


def run_check(
    source: Path,
    dest: Path,
    items: list[CopyItem],
    *,
    workers: int,
    fsync: bool,
    use_hash: bool,
) -> bool:
    """Copy and verify once. Prints one line. Returns True when the copy verified."""
    total = sum(i.size for i in items)
    t0 = time.perf_counter()
    copy = copy_files(source, dest, items, workers=workers, hash_source=use_hash, fsync=fsync)
    t1 = time.perf_counter()
    result = verify_copy(
        source,
        dest,
        items,
        hash_mode=HashMode.ALL if use_hash else HashMode.NONE,
        sample_fraction=1.0,
        source_hashes=copy.source_hashes,
    )
    t2 = time.perf_counter()
    passed = copy.ok and result.passed
    per_file = (t1 - t0) / len(items) * 1000
    print(
        f"{'PASS' if passed else 'FAIL'}  {workers:2d} at once  flush {'on ' if fsync else 'off'}  "
        f"copy {t1 - t0:8.1f} s {_rate(total, t1 - t0)} {per_file:7.2f} ms/file  "
        f"check {t2 - t1:7.1f} s",
        flush=True,
    )
    for failure in copy.failed[:5]:
        print(f"      {failure.rel_path}: {failure.message}")
    for problem in result.problems[:5]:
        print(f"      {problem.rel_path}: {problem.message}")
    return passed


def _parser(prog: str | None = None) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description="Measure the copy engine's throughput to a folder (DECISIONS.md D48, D54).",
    )
    p.add_argument("dest_dir", type=Path, help="new or empty folder at the destination")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--source", type=Path, help="copy every file under this folder")
    source.add_argument(
        "--make-source", type=Path, metavar="WORK_DIR", help="write random files here first"
    )
    p.add_argument("--files", type=int, default=10, help="with --make-source (default 10)")
    p.add_argument("--file-mb", type=float, default=200.0, help="with --make-source (default 200)")
    p.add_argument(
        "--workers", type=int, nargs="+", default=[1, 4, 8], help="files at once (default 1 4 8)"
    )
    p.add_argument("--fsync", choices=sorted(FSYNC_CHOICES), default="both")
    p.add_argument("--hash", action="store_true", help="hash every file and compare")
    return p


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    args = _parser(prog).parse_args(argv)
    try:
        if args.files < 1 or args.file_mb <= 0 or any(w < 1 for w in args.workers):
            raise UsageError("--files, --file-mb and --workers must be positive")
        _new_or_empty(args.dest_dir, "DEST_DIR")
        if args.make_source is not None:
            _new_or_empty(args.make_source, "WORK_DIR")
        elif not args.source.is_dir():
            raise UsageError(f"the source folder does not exist: {args.source}")
    except UsageError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    if args.make_source is not None:
        file_bytes = max(1, round(args.file_mb * MB))
        print(f"Writing {args.files} source files of {file_bytes / MB:g} MB in {args.make_source}")
        source = make_source(args.make_source, args.files, file_bytes)
    else:
        source = args.source
    items = list_source(source)
    if not items:
        print(f"ERROR the source folder holds no files: {source}", file=sys.stderr)
        return 2
    total = sum(i.size for i in items)
    print(f"Copying {len(items):,} files, {total / MB:g} MB, to {args.dest_dir} for each run")
    all_passed = True
    with keep_awake():
        for workers in dict.fromkeys(args.workers):
            for fsync in FSYNC_CHOICES[args.fsync]:
                dest = args.dest_dir / f"workers-{workers}-fsync-{'on' if fsync else 'off'}"
                all_passed &= run_check(
                    source, dest, items, workers=workers, fsync=fsync, use_hash=args.hash
                )
    print(f"Done. Remove {args.dest_dir} by hand when you no longer need it.")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
