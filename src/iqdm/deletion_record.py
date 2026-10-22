"""The record of a deleted catalogue entry (DECISIONS.md D89).

Before the Log tab deletes an entry, it writes the whole entry to a JSON file in the
deleted-entries folder next to the configuration file, as manifests are kept
(D52). The file holds the recording's fields, channels and RF chain, and the check
rows deleted with it, so an administrator can enter it again by hand. The record
stays on the PC that deleted the entry. write_record() creates the file and never
replaces an existing one.
"""

import json
import os
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from iqdm.models import Recording, TransferEntry

FORMAT = "iqdm-deleted-entry"
VERSION = 1
RECORDS_DIR_NAME = "deleted-entries"


class DeletionRecordError(OSError):
    """The record cannot be written. The entry is then not deleted."""


def records_dir(config_path: Path) -> Path:
    """The deleted-entries folder next to the configuration file."""
    return config_path.parent / RECORDS_DIR_NAME


def record_name(recording_id: int, deleted_at: str) -> str:
    """'recording-12-20261023T080000Z.json'. The time keeps two databases apart."""
    stamp = "".join(c for c in deleted_at if c.isalnum())
    return f"recording-{recording_id}-{stamp}.json"


def to_bytes(
    recording: Recording,
    transfers: Sequence[TransferEntry],
    *,
    database: str,
    deleted_by: str,
    deleted_at: str,
) -> bytes:
    data: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "deleted_at": deleted_at,
        "deleted_by": deleted_by,
        "database": database,
        "recording": asdict(recording),
        "transfers": [asdict(t) for t in transfers],
    }
    return (json.dumps(data, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def write_record(
    folder: Path,
    recording: Recording,
    transfers: Sequence[TransferEntry],
    *,
    database: str,
    deleted_by: str,
    deleted_at: str,
) -> Path:
    """Write the record to a new file in `folder` and return its path.

    The folder is created if missing. An existing file is never replaced.
    """
    if recording.id is None:
        raise ValueError("a record needs a stored recording")
    data = to_bytes(
        recording, transfers, database=database, deleted_by=deleted_by, deleted_at=deleted_at
    )
    path = folder / record_name(recording.id, deleted_at)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    except FileExistsError:
        raise DeletionRecordError(
            f"A record of a deleted entry already exists at {path}. Try again in a minute."
        ) from None
    except OSError as exc:
        raise DeletionRecordError(
            f"The copy of the entry could not be saved in {folder}: {exc}"
        ) from exc
    return path
