"""Create the synthetic test set for the NAS field test with the Milestone 6 build (D54).

The NAS is reachable only from the recording laptops, so the first transfer test on it
runs with the Milestone 6 build. This tool writes a folder of synthetic recordings on
the laptop's local disk. Each recording covers some of the cases that the test must
show: large files, many small files, gaps and time ranges, a single-channel .bin
recording with a short last file, and half-second files. All files hold random bytes,
so a NAS that compresses data on its disks cannot make a copy look faster than it is.

The tool writes TESTSET.md with the recordings and what to test with each, and
testset.json with the ground truth (file counts, sizes, gaps) for every recording.

The code moved here from tools/make_nas_testset.py, which stays as a wrapper (D57).

Usage, in the packaged app or from the repository:
    IQDataManager-check.exe make-test-set OUT_DIR [--large-files N] [--large-mb MB]
                                                  [--small-files N] [--quick]
    python tools/make_nas_testset.py OUT_DIR [--large-files N] [--large-mb MB]
                                             [--small-files N] [--quick]

OUT_DIR must be a new or empty folder on a local disk. The default set holds
5.05 GB. --quick writes a set of 67.8 MB with the same structure, for a first look.
The tool never deletes anything; remove OUT_DIR by hand afterwards.

Exit codes: 0 success, 1 output folder refused, 2 usage error.
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from iqdm.diagnostics.fixtures import (
    DEFAULT_START_UNIX,
    ChannelSpec,
    FixtureInfo,
    OutputRefusedError,
    RecordingSpec,
    make_recording,
)

DAY_S = 86400
BYTES_PER_COMPLEX_SAMPLE = 4  # int16 I and Q
CHECK_EXE = "IQDataManager-check.exe"


@dataclass(frozen=True, kw_only=True)
class SetSizes:
    """File counts and sizes. Sizes are in bytes per file."""

    large_files: int = 10  # per channel
    large_file_bytes: int = 200_000_000  # 50 MS/s, int16, 1 s
    small_files: int = 2000  # per channel
    small_file_bytes: int = 64_000  # 16 kS/s, int16, 1 s
    mid_files: int = 300  # the gaps recording, per channel
    mid_file_bytes: int = 1_000_000  # 250 kS/s, int16, 1 s


QUICK = SetSizes(
    large_files=4,
    large_file_bytes=4_000_000,
    small_files=200,
    small_file_bytes=4_000,
    mid_files=60,
    mid_file_bytes=100_000,
)


@dataclass(frozen=True, kw_only=True)
class SetRecording:
    folder: str
    spec: RecordingSpec
    covers: str


def _fs(file_bytes: int, file_duration_s: float = 1.0) -> float:
    """Sample rate that gives files of file_bytes (int16, no header)."""
    samples = file_bytes // BYTES_PER_COMPLEX_SAMPLE
    if samples < 2 or file_bytes % BYTES_PER_COMPLEX_SAMPLE:
        raise ValueError(f"file size must be a multiple of 4 bytes and at least 8: {file_bytes}")
    return samples / file_duration_s


def recordings(sizes: SetSizes) -> list[SetRecording]:
    """The recordings of the test set, each starting on its own day."""
    mid = sizes.mid_files
    mid_fs = _fs(sizes.mid_file_bytes)
    return [
        SetRecording(
            folder="A-large-files",
            spec=RecordingSpec(
                n_channels=2,
                n_slots=sizes.large_files,
                start_unix=DEFAULT_START_UNIX,
                fs_hz=_fs(sizes.large_file_bytes),
                content="random",
            ),
            covers=(
                "Throughput with large files; 1, 4 and 8 files at once; flush on and off. "
                "Archive to the NAS, stop half-way and resume, check before delete, then "
                "delete the laptop copy."
            ),
        ),
        SetRecording(
            folder="B-small-files",
            spec=RecordingSpec(
                n_channels=2,
                n_slots=sizes.small_files,
                start_unix=DEFAULT_START_UNIX + DAY_S,
                fs_hz=_fs(sizes.small_file_bytes),
                content="random",
            ),
            covers=(
                "Cost per file: many small files; 1, 4 and 8 files at once; flush on and "
                "off. Archive and check."
            ),
        ),
        SetRecording(
            folder="C-gaps-and-ranges",
            spec=RecordingSpec(
                n_channels=2,
                n_slots=mid,
                start_unix=DEFAULT_START_UNIX + 2 * DAY_S,
                fs_hz=mid_fs,
                content="random",
                channels={
                    0: ChannelSpec(gaps=frozenset(range(mid // 6, mid // 6 + 10)) | {mid * 2 // 3}),
                    1: ChannelSpec(first_slot=mid // 10),
                },
            ),
            covers=(
                "Copy of a time range and of one channel to the PC; the preview's missing "
                "seconds and timeline; channel 1 starts later than channel 0."
            ),
        ),
        SetRecording(
            folder="D-bin-single-channel",
            spec=RecordingSpec(
                n_channels=1,
                n_slots=120,
                start_unix=DEFAULT_START_UNIX + 3 * DAY_S,
                fs_hz=mid_fs,
                ext=".bin",
                flat=True,
                content="random",
                wrong_size={119: None},  # a short last file, as when a capture stops
            ),
            covers=(
                ".bin files in the recording folder itself, with a short last file. "
                "Log, archive, check and delete."
            ),
        ),
        SetRecording(
            folder="E-half-second-files",
            spec=RecordingSpec(
                n_channels=1,
                n_slots=240,
                start_unix=DEFAULT_START_UNIX + 4 * DAY_S,
                file_duration_s=0.5,
                fs_hz=_fs(sizes.mid_file_bytes // 2, 0.5),
                content="random",
            ),
            covers=(
                "File names with fractional seconds; a time range that starts and ends "
                "between two files."
            ),
        ),
    ]


def _check_out_dir(out_dir: Path) -> None:
    if str(out_dir).startswith(("\\\\", "//")):
        raise OutputRefusedError(f"write the test set to a local disk, not {out_dir}")
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        raise OutputRefusedError(f"output folder must be new or empty: {out_dir}")


def _size_text(n_bytes: int) -> str:
    """'4.00 GB', '200.0 MB', '64.0 kB' (powers of 10)."""
    if n_bytes >= 1e9:
        return f"{n_bytes / 1e9:.2f} GB"
    if n_bytes >= 1e6:
        return f"{n_bytes / 1e6:.1f} MB"
    return f"{n_bytes / 1e3:.1f} kB"


def _readme(made: list[tuple[SetRecording, FixtureInfo]]) -> str:
    lines = [
        "# NAS field test set",
        "",
        "Synthetic recordings for the first transfer test on the NAS with the Milestone 6",
        "build (DECISIONS.md D54). Every file holds random bytes. Ground truth is in",
        "`testset.json`.",
        "",
        "Use a scratch database and a scratch folder on the NAS. Never use the real",
        "catalogue for this test.",
        "",
        "| Folder | Channels | Files per channel | File size | Total | What to test |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for rec, info in made:
        counts = ", ".join(str(c.n_files) for c in info.channels)
        total = sum(c.total_bytes for c in info.channels)
        lines.append(
            f"| `{rec.folder}` | {len(info.channels)} | {counts} | "
            f"{_size_text(info.channels[0].expected_file_bytes)} | {_size_text(total)} | "
            f"{rec.covers} |"
        )
    lines += [
        "",
        "## Order of the test",
        "",
        "1. Database locking on the NAS (O21), with a scratch database, from two PCs:",
        f"   `{CHECK_EXE} db-check`.",
        f"2. Throughput: `{CHECK_EXE} copy-check` on `A-large-files` and `B-small-files`,",
        "   with 1, 4 and 8 files at once, and with the flush on and off.",
        "3. Log each recording in the scratch database.",
        "4. Copy part of `C-gaps-and-ranges` and of `E-half-second-files` to the PC.",
        "5. Archive `A-large-files`: stop it half-way, resume it from \"Unfinished",
        "   transfers\", and check that it resumes. Then archive `B-small-files` and",
        "   `D-bin-single-channel`.",
        "6. Check each archive with \"Check archive\" and \"Check before delete\". Delete",
        "   the laptop copy of `D-bin-single-channel` first, then of the others.",
        "",
        "The Milestone 6 report gives the exact steps and the expected results.",
        "",
    ]
    return "\n".join(lines)


DEFAULT_SIZES = SetSizes()


def make_testset(out_dir: Path, sizes: SetSizes = DEFAULT_SIZES) -> list[FixtureInfo]:
    """Write the test set into out_dir. Raises OutputRefusedError for a used folder."""
    _check_out_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for rec in recordings(sizes):
        print(f"Writing {rec.folder} ...", flush=True)
        made.append((rec, make_recording(out_dir / rec.folder, rec.spec)))
    (out_dir / "testset.json").write_text(
        json.dumps({rec.folder: asdict(info) for rec, info in made}, indent=1),
        encoding="utf-8",
    )
    (out_dir / "TESTSET.md").write_text(_readme(made), encoding="utf-8")
    return [info for _, info in made]


def _parser(prog: str | None = None) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog, description="Create the NAS field test set (DECISIONS.md D54)."
    )
    p.add_argument("out_dir", type=Path, help="new or empty folder on a local disk")
    p.add_argument("--quick", action="store_true", help="67.8 MB with the same structure")
    p.add_argument("--large-files", type=int, help="files per channel in A (default 10)")
    p.add_argument("--large-mb", type=float, help="MB per file in A (default 200)")
    p.add_argument("--small-files", type=int, help="files per channel in B (default 2000)")
    return p


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    args = _parser(prog).parse_args(argv)
    sizes = QUICK if args.quick else SetSizes()
    changes = {}
    if args.large_files is not None:
        changes["large_files"] = args.large_files
    if args.large_mb is not None:
        changes["large_file_bytes"] = round(args.large_mb * 1e6 / 4) * 4
    if args.small_files is not None:
        changes["small_files"] = args.small_files
    try:
        sizes = SetSizes(**(asdict(sizes) | changes))
        if min(sizes.large_files, sizes.small_files) < 1:
            raise ValueError("file counts must be at least 1")
        recordings(sizes)  # checks the sizes before anything is written
    except ValueError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    try:
        infos = make_testset(args.out_dir, sizes)
    except OutputRefusedError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    total = sum(c.total_bytes for info in infos for c in info.channels)
    print(f"Done: {len(infos)} recordings, {_size_text(total)} in {args.out_dir}.")
    print("Remove the folder by hand after the test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
