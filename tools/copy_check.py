"""Measure the copy engine's throughput to a folder, for example a scratch folder on the NAS.

DECISIONS.md D48: the app copies files itself. Before Milestone 6 the user runs this
tool from a laptop to a scratch folder on the NAS. It shows how fast the engine copies
with 1, 4 and 8 files at once, and whether the copies verify. The tool uses the app's
own copy engine and verification, so it tests the code the app will run.

Usage:
    python tools/copy_check.py WORK_DIR DEST_DIR [--files N] [--file-mb MB]
                               [--workers 1 4 8] [--hash]

- WORK_DIR: a new or empty folder on the local disk. The tool writes the source files
  there: N files of random bytes, MB megabytes each (10**6 bytes).
- DEST_DIR: a new or empty folder at the destination. Each run copies into its own
  subfolder, DEST_DIR/workers-<n>.
- --hash: compute SHA-256 during the copy and compare every file afterwards.

Large files (200 MB, as at 50 MS/s) and small files (for example 0.064 MB, as at
16 kS/s) behave differently. Run the tool once for each.

The tool never deletes anything. Remove WORK_DIR and DEST_DIR by hand afterwards.
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


class UsageError(Exception):
    """A folder or an argument cannot be used."""


def _new_or_empty(path: Path, label: str) -> None:
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise UsageError(f"{label} must be a new or empty folder: {path}")


def make_source(work_dir: Path, n_files: int, file_bytes: int) -> list[CopyItem]:
    """Write n_files of random bytes into work_dir/source/0 and list them."""
    folder = work_dir / "source" / "0"
    folder.mkdir(parents=True)
    items = []
    for i in range(n_files):
        name = f"{FIRST_STAMP + i}.dat"
        with (folder / name).open("xb") as f:
            left = file_bytes
            while left > 0:
                block = min(WRITE_BLOCK, left)
                f.write(os.urandom(block))
                left -= block
        items.append(CopyItem(rel_path=f"0/{name}", size=file_bytes))
    return items


def _rate(n_bytes: int, seconds: float) -> str:
    return f"{n_bytes / MB / seconds:8.1f} MB/s" if seconds > 0 else "       - MB/s"


def run_check(
    source: Path, dest: Path, items: list[CopyItem], workers: int, use_hash: bool
) -> bool:
    """Copy and verify once. Prints one line. Returns True when the copy verified."""
    total = sum(i.size for i in items)
    t0 = time.perf_counter()
    copy = copy_files(source, dest, items, workers=workers, hash_source=use_hash)
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
    status = "PASS" if passed else "FAIL"
    print(
        f"{status}  {workers:2d} at once  copy {t1 - t0:8.1f} s {_rate(total, t1 - t0)}  "
        f"check {t2 - t1:7.1f} s",
        flush=True,
    )
    for failure in copy.failed[:5]:
        print(f"      {failure.rel_path}: {failure.message}")
    for problem in result.problems[:5]:
        print(f"      {problem.rel_path}: {problem.message}")
    return passed


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Measure the copy engine's throughput to a folder (DECISIONS.md D48)."
    )
    p.add_argument("work_dir", type=Path, help="new or empty local folder for the source files")
    p.add_argument("dest_dir", type=Path, help="new or empty folder at the destination")
    p.add_argument("--files", type=int, default=10, help="number of files (default 10)")
    p.add_argument("--file-mb", type=float, default=200.0, help="MB per file (default 200)")
    p.add_argument(
        "--workers", type=int, nargs="+", default=[1, 4, 8], help="files at once (default 1 4 8)"
    )
    p.add_argument("--hash", action="store_true", help="hash every file and compare")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.files < 1 or args.file_mb <= 0 or any(w < 1 for w in args.workers):
            raise UsageError("--files, --file-mb and --workers must be positive")
        _new_or_empty(args.work_dir, "WORK_DIR")
        _new_or_empty(args.dest_dir, "DEST_DIR")
    except UsageError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    file_bytes = max(1, round(args.file_mb * MB))
    print(f"Writing {args.files} source files of {file_bytes / MB:g} MB in {args.work_dir}")
    items = make_source(args.work_dir, args.files, file_bytes)
    source = args.work_dir / "source"
    print(f"Copying {args.files * file_bytes / MB:g} MB to {args.dest_dir} for each run")
    all_passed = True
    with keep_awake():
        for workers in args.workers:
            dest = args.dest_dir / f"workers-{workers}"
            if dest.exists():
                print(f"SKIP  {workers:2d} at once: {dest} already exists")
                continue
            all_passed &= run_check(source, dest, items, workers, args.hash)
    print(f"Done. Remove {args.work_dir} and {args.dest_dir} by hand when you no longer need them.")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
