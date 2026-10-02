"""Per-machine configuration file (SPEC section 4).

Until Milestone 7 the app only reads the file (DECISIONS.md D15). A missing file gives
the defaults. Unknown keys are ignored. A wrong type or value raises ConfigError,
which names the file and the key.
"""

import math
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

from iqdm.models import HashMode

CONFIG_DIR_NAME = "IQDataManager"
CONFIG_FILE_NAME = "config.toml"


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


def _nas_roots(data: Mapping[str, Any], where: str) -> tuple[str, ...]:
    value = data.get("nas_roots", [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where}: nas_roots must be a list of strings")
    roots = []
    for v in value:
        if not is_unc_path(v):
            raise ConfigError(f"{where}: nas_roots entry {v!r} is not a UNC path")
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
        storage_roots=_storage_roots(data, where),
    )


def load_config(path: Path) -> Config:
    """Read a configuration file. A missing file gives the defaults."""
    if not path.exists():
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: not valid TOML: {exc}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path}: cannot read the file: {exc}") from exc
    return parse_config(data, str(path))
