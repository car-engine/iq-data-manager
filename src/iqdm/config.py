"""Per-machine configuration file (SPEC section 4).

A missing file gives the defaults. Unknown keys are ignored. A wrong type or value
raises ConfigError, which names the file and the key (DECISIONS.md D15).

The Settings tab writes the file through save_config() with tomli-w (Milestone 3a,
O18). The tab shows three keys (SETTINGS_KEYS). Every other key in the file is kept
as it was. Comments are lost.
"""

import math
import os
import shutil
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

import tomli_w

from iqdm.models import HashMode

CONFIG_DIR_NAME = "IQDataManager"
CONFIG_FILE_NAME = "config.toml"
NEW_SUFFIX = ".new"  # written first, then renamed over config.toml
BACKUP_SUFFIX = ".bak"  # the file as it was before the last Save (O31)
SETTINGS_KEYS = ("db_path", "nas_roots", "display_utc_offset_hours")  # shown in the Settings tab
OFFSET_MIN_HOURS = -12.0
OFFSET_MAX_HOURS = 14.0
OFFSET_STEP_HOURS = 0.25


class ConfigError(Exception):
    """The configuration file cannot be read or holds a wrong value."""


@dataclass(frozen=True, kw_only=True)
class Config:
    """Settings from config.toml. db_path None means no database is configured."""

    db_path: str | None = None
    default_local_copy_root: str | None = None
    network_speed_mb_s: float = 110.0
    default_hash_mode: HashMode = HashMode.SAMPLE
    hash_sample_fraction: float = 0.05
    nas_roots: tuple[str, ...] = ()  # UNC roots, without a trailing separator (D14)
    display_utc_offset_hours: float = 8.0  # displayed times only; storage stays UTC (D24)
    storage_roots: Mapping[str, str] = field(default_factory=dict)


def default_config_path(environ: Mapping[str, str] | None = None) -> Path:
    """%APPDATA%\\IQDataManager\\config.toml. Raises ConfigError if APPDATA is not set."""
    env = os.environ if environ is None else environ
    appdata = env.get("APPDATA")
    if not appdata:
        raise ConfigError("the APPDATA environment variable is not set")
    return Path(appdata) / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def is_unc_path(text: str) -> bool:
    """True for a UNC path with a server and a share, such as \\\\server\\share\\folder.

    Device paths such as \\\\?\\C:\\ and \\\\.\\C:\\ are not UNC paths here.
    """
    drive = PureWindowsPath(text).drive
    if not drive.startswith("\\\\"):
        return False
    parts = drive.strip("\\").split("\\")
    return len(parts) == 2 and parts[0] not in ("?", ".") and all(parts)


def _clean_root(text: str) -> str:
    """Backslashes and no trailing separator. Letter case is kept."""
    return text.replace("/", "\\").rstrip("\\")


def _optional_str(data: Mapping[str, Any], key: str, where: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: {key} must be a non-empty string")
    return value.strip()


def _number(data: Mapping[str, Any], key: str, where: str, default: float) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ConfigError(f"{where}: {key} must be a number")
    return float(value)


def nas_root_error(text: str) -> str | None:
    """Why `text` cannot be a nas_roots entry, or None if it can (D14)."""
    if not is_unc_path(text):
        return f"nas_roots entry '{text}' is not a UNC path"  # no repr: it doubles backslashes
    return None


def offset_error(hours: float) -> str | None:
    """Why `hours` cannot be display_utc_offset_hours, or None if it can (D24)."""
    if not OFFSET_MIN_HOURS <= hours <= OFFSET_MAX_HOURS or (hours / OFFSET_STEP_HOURS) % 1:
        return "display_utc_offset_hours must be between -12 and 14 in steps of 0.25"
    return None


def _nas_roots(data: Mapping[str, Any], where: str) -> tuple[str, ...]:
    value = data.get("nas_roots", [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where}: nas_roots must be a list of strings")
    roots = []
    for v in value:
        error = nas_root_error(v)
        if error is not None:
            raise ConfigError(f"{where}: {error}")
        roots.append(_clean_root(v))
    return tuple(roots)


def _storage_roots(data: Mapping[str, Any], where: str) -> dict[str, str]:
    value = data.get("storage_roots", {})
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise ConfigError(f"{where}: storage_roots must be a table of strings")
    return dict(value)


def parse_config(data: Mapping[str, Any], where: str) -> Config:
    """Build a Config from parsed TOML. `where` names the source in error messages."""
    speed = _number(data, "network_speed_mb_s", where, Config.network_speed_mb_s)
    if speed <= 0:
        raise ConfigError(f"{where}: network_speed_mb_s must be positive")
    fraction = _number(data, "hash_sample_fraction", where, Config.hash_sample_fraction)
    if not 0 < fraction <= 1:
        raise ConfigError(f"{where}: hash_sample_fraction must be above 0 and at most 1")
    offset = _number(data, "display_utc_offset_hours", where, Config.display_utc_offset_hours)
    error = offset_error(offset)
    if error is not None:
        raise ConfigError(f"{where}: {error}")
    mode_text = data.get("default_hash_mode", str(Config.default_hash_mode))
    try:
        mode = HashMode(mode_text)
    except ValueError:
        choices = ", ".join(m.value for m in HashMode)
        raise ConfigError(f"{where}: default_hash_mode must be one of {choices}") from None
    return Config(
        db_path=_optional_str(data, "db_path", where),
        default_local_copy_root=_optional_str(data, "default_local_copy_root", where),
        network_speed_mb_s=speed,
        default_hash_mode=mode,
        hash_sample_fraction=fraction,
        nas_roots=_nas_roots(data, where),
        display_utc_offset_hours=offset,
        storage_roots=_storage_roots(data, where),
    )


def read_config_data(path: Path) -> dict[str, Any]:
    """The parsed TOML of a configuration file, unchecked. A missing file gives {}."""
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: not valid TOML: {exc}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path}: cannot read the file: {exc}") from exc


def load_config(path: Path) -> Config:
    """Read a configuration file. A missing file gives the defaults."""
    return parse_config(read_config_data(path), str(path))


# =========================================================================
# Writing (Settings tab, Milestone 3a)
# =========================================================================


@dataclass(frozen=True, kw_only=True)
class SettingsInput:
    """The keys the Settings tab shows, as the user entered them.

    db_path "" means no database path. NAS roots are kept as typed until they are
    written.
    """

    db_path: str = ""
    nas_roots: tuple[str, ...] = ()
    display_utc_offset_hours: float = Config.display_utc_offset_hours


def settings_from_data(data: Mapping[str, Any]) -> SettingsInput:
    """The shown keys of parsed TOML, as far as they have the right type.

    A value of the wrong type gives the default for that field, so the tab can still
    open on a file that parse_config() refuses.
    """
    db = data.get("db_path")
    roots = data.get("nas_roots")
    offset = data.get("display_utc_offset_hours")
    if isinstance(offset, bool) or not isinstance(offset, int | float):
        offset = Config.display_utc_offset_hours
    return SettingsInput(
        db_path=db.strip() if isinstance(db, str) else "",
        nas_roots=tuple(r for r in roots if isinstance(r, str)) if isinstance(roots, list) else (),
        display_utc_offset_hours=float(offset),
    )


def settings_errors(settings: SettingsInput) -> dict[str, str]:
    """Errors by key, with the same rules as parse_config(). Empty when all are valid."""
    errors = {}
    root_errors = [e for e in map(nas_root_error, _stripped(settings.nas_roots)) if e]
    if root_errors:
        errors["nas_roots"] = root_errors[0]
    error = offset_error(settings.display_utc_offset_hours)
    if error is not None:
        errors["display_utc_offset_hours"] = error
    return errors


def hidden_key_error(data: Mapping[str, Any], where: str) -> str | None:
    """The error in a key the Settings tab does not show, or None.

    Save is blocked while such a key is wrong, because the app would write a file it
    cannot read back. The user corrects the key by hand.
    """
    try:
        parse_config({k: v for k, v in data.items() if k not in SETTINGS_KEYS}, where)
    except ConfigError as exc:
        return str(exc)
    return None


def _stripped(roots: Sequence[str]) -> list[str]:
    return [r.strip() for r in roots]


def merge_settings(data: Mapping[str, Any], settings: SettingsInput) -> dict[str, Any]:
    """`data` with the shown keys replaced by `settings`. Every other key stays.

    A blank db_path removes the key. NAS roots lose a trailing separator. A whole
    number of hours is written as an integer.
    """
    merged = dict(data)
    db = settings.db_path.strip()
    if db:
        merged["db_path"] = db
    else:
        merged.pop("db_path", None)
    merged["nas_roots"] = [_clean_root(r) for r in _stripped(settings.nas_roots)]
    offset = float(settings.display_utc_offset_hours)
    merged["display_utc_offset_hours"] = int(offset) if offset.is_integer() else offset
    return merged


def backup_path(path: Path) -> Path:
    """config.toml.bak next to the configuration file (O31)."""
    return path.with_name(path.name + BACKUP_SUFFIX)


def save_config(path: Path, data: Mapping[str, Any]) -> Config:
    """Write `data` to `path` and return the Config it holds.

    The data is checked first, and the TOML text is read back before anything is
    written. The text goes to config.toml.new in the same folder. The old file is
    copied to config.toml.bak, and config.toml.new then replaces config.toml. A
    failure before that last step leaves config.toml unchanged. A missing folder is
    created.
    """
    where = str(path)
    config = parse_config(data, where)
    try:
        text = tomli_w.dumps(dict(data))
    except TypeError as exc:
        raise ConfigError(f"{where}: cannot write the value: {exc}") from exc
    if parse_config(tomllib.loads(text), where) != config:
        raise ConfigError(f"{where}: the written text does not read back the same")
    new_path = path.with_name(path.name + NEW_SUFFIX)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        new_path.write_text(text, encoding="utf-8")
        if path.exists():
            shutil.copy2(path, backup_path(path))
        new_path.replace(path)
    except OSError as exc:
        raise ConfigError(f"{where}: cannot write the file: {exc}") from exc
    return config
