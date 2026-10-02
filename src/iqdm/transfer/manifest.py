"""Per-file manifest of a copy or a move (DECISIONS.md D52, SPEC section 8).

The manifest lists every file a transfer copied, with its size and its SHA-256 where
one was computed. It is a JSON file named transfer-<id>-<time>.json in the manifests folder
next to the configuration file. write_manifest() creates it and never replaces an
existing file. transfer_log.manifest_sha256 holds the SHA-256 of its bytes, and
read_manifest() refuses a file that no longer matches it.

Relative paths are '/'-separated and must stay inside the recording folder.
delete.py relies on safe_rel_path() for that.
"""

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iqdm.models import HashMode, Operation

FORMAT = "iqdm-manifest"
VERSION = 1
MANIFESTS_DIR_NAME = "manifests"


class ManifestError(ValueError):
    """The manifest cannot be written, read or trusted."""


@dataclass(frozen=True, kw_only=True)
class ManifestFile:
    path: str  # relative to the recording folder, '/'-separated
    size: int
    sha256: str | None = None  # lower-case hex; None when the file was not hashed


@dataclass(frozen=True, kw_only=True)
class Manifest:
    transfer_id: int
    recording_id: int
    operation: Operation
    source: str
    destination: str
    range_start_unix: float | None
    range_end_unix: float | None
    channels: tuple[int, ...] | None
    hash_mode: HashMode
    created_at: str
    files: tuple[ManifestFile, ...]

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)


def manifests_dir(config_path: Path) -> Path:
    """The manifests folder next to the configuration file."""
    return config_path.parent / MANIFESTS_DIR_NAME


def manifest_name(transfer_id: int, created_at: str) -> str:
    """'transfer-7-20261003T080000Z.json'.

    The time keeps names apart when two databases on one PC reuse a transfer id, for
    example a test catalogue and the real one.
    """
    stamp = "".join(c for c in created_at if c.isalnum())
    return f"transfer-{transfer_id}-{stamp}.json"


def safe_rel_path(text: str) -> str:
    """`text` if it is a '/'-separated path inside its folder, else ManifestError.

    Refused: empty text, a leading or doubled '/', backslashes, '.' and '..'
    components, and ':' (a drive or an alternate data stream).
    """
    if not isinstance(text, str) or not text:
        raise ManifestError(f"not a relative path: {text!r}")
    parts = text.split("/")
    if any(p in ("", ".", "..") for p in parts) or "\\" in text or ":" in text:
        raise ManifestError(f"not a relative path inside the recording folder: {text!r}")
    return text


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def to_bytes(manifest: Manifest) -> bytes:
    data: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "transfer_id": manifest.transfer_id,
        "recording_id": manifest.recording_id,
        "operation": str(manifest.operation),
        "source": manifest.source,
        "destination": manifest.destination,
        "range_start_unix": manifest.range_start_unix,
        "range_end_unix": manifest.range_end_unix,
        "channels": None if manifest.channels is None else list(manifest.channels),
        "hash_mode": str(manifest.hash_mode),
        "created_at": manifest.created_at,
        "files": [{"path": f.path, "size": f.size, "sha256": f.sha256} for f in manifest.files],
    }
    return (json.dumps(data, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def write_manifest(manifest: Manifest, folder: Path) -> tuple[Path, str]:
    """Write the manifest to a new file in `folder`. Returns its path and SHA-256.

    The folder is created if missing. An existing file is never replaced.
    """
    for f in manifest.files:
        safe_rel_path(f.path)
    data = to_bytes(manifest)
    path = folder / manifest_name(manifest.transfer_id, manifest.created_at)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    except FileExistsError:
        raise ManifestError(f"a manifest already exists at {path}") from None
    except OSError as exc:
        raise ManifestError(f"cannot write the manifest {path}: {exc}") from exc
    return path, sha256_hex(data)


def _wrong(key: str) -> ManifestError:
    return ManifestError(f"manifest field {key!r} is missing or has the wrong type")


def _int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise _wrong(key)
    return value


def _str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise _wrong(key)
    return value


def _optional_number(data: dict[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ManifestError(f"manifest field {key!r} has the wrong type")
    return float(value)


def _channels(value: object) -> tuple[int, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(
        isinstance(i, int) and not isinstance(i, bool) and i >= 0 for i in value
    ):
        raise ManifestError("manifest field 'channels' has the wrong type")
    return tuple(value)


def _files(value: object) -> tuple[ManifestFile, ...]:
    if not isinstance(value, list):
        raise ManifestError("manifest field 'files' has the wrong type")
    files = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ManifestError("a manifest file entry is not an object")
        path = safe_rel_path(item.get("path"))
        size = item.get("size")
        digest = item.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ManifestError(f"manifest entry {path!r} has no valid size")
        if digest is not None and (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ManifestError(f"manifest entry {path!r} has no valid SHA-256")
        if path.casefold() in seen:
            raise ManifestError(f"manifest lists {path!r} twice")
        seen.add(path.casefold())
        files.append(ManifestFile(path=path, size=size, sha256=digest))
    return tuple(files)


def parse_manifest(data: bytes) -> Manifest:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"the manifest is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise ManifestError("the file is not an IQ Data Manager manifest")
    if raw.get("version") != VERSION:
        raise ManifestError(f"unknown manifest version {raw.get('version')!r}")
    try:
        operation = Operation(_str(raw, "operation"))
        hash_mode = HashMode(_str(raw, "hash_mode"))
    except ValueError as exc:
        raise ManifestError(f"manifest field has an unknown value: {exc}") from exc
    return Manifest(
        transfer_id=_int(raw, "transfer_id"),
        recording_id=_int(raw, "recording_id"),
        operation=operation,
        source=_str(raw, "source"),
        destination=_str(raw, "destination"),
        range_start_unix=_optional_number(raw, "range_start_unix"),
        range_end_unix=_optional_number(raw, "range_end_unix"),
        channels=_channels(raw.get("channels")),
        hash_mode=hash_mode,
        created_at=_str(raw, "created_at"),
        files=_files(raw.get("files")),
    )


def read_manifest(path: Path, expected_sha256: str | None = None) -> Manifest:
    """Read and check a manifest. With expected_sha256, refuse a changed file."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ManifestError(f"cannot read the manifest {path}: {exc}") from exc
    if expected_sha256 is not None and sha256_hex(data) != expected_sha256:
        raise ManifestError(f"the manifest {path} changed after it was written")
    return parse_manifest(data)


def manifest_files(
    paths_and_sizes: Sequence[tuple[str, int]], hashes: dict[str, str]
) -> tuple[ManifestFile, ...]:
    """ManifestFile entries in the given order, with the hashes that exist."""
    return tuple(ManifestFile(path=p, size=s, sha256=hashes.get(p)) for p, s in paths_and_sizes)
