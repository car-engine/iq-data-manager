"""Tests for iqdm.config. Every configuration file lives in tmp_path."""

from pathlib import Path

import pytest

from iqdm.config import (
    Config,
    ConfigError,
    default_config_path,
    is_unc_path,
    load_config,
)
from iqdm.models import HashMode


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_gives_defaults(tmp_path):
    config = load_config(tmp_path / "absent.toml")
    assert config == Config()
    assert config.db_path is None
    assert config.nas_roots == ()


def test_empty_file_gives_defaults(tmp_path):
    assert load_config(write(tmp_path, "")) == Config()


def test_reads_every_key(tmp_path):
    path = write(
        tmp_path,
        r"""
db_path = 'D:\data\catalog.db'
default_local_copy_root = 'D:\work\iq'
network_speed_mb_s = 95
default_hash_mode = "all"
hash_sample_fraction = 0.1
nas_roots = ['\\nas\recordings', '\\nas2\archive\iq']

[storage_roots]
'\\nas\recordings' = '/mnt/nas/recordings'
""",
    )
    config = load_config(path)
    assert config.db_path == r"D:\data\catalog.db"
    assert config.default_local_copy_root == r"D:\work\iq"
    assert config.network_speed_mb_s == 95.0
    assert config.default_hash_mode is HashMode.ALL
    assert config.hash_sample_fraction == 0.1
    assert config.nas_roots == (r"\\nas\recordings", r"\\nas2\archive\iq")
    assert config.storage_roots == {r"\\nas\recordings": "/mnt/nas/recordings"}


def test_nas_roots_lose_trailing_separator_and_keep_case(tmp_path):
    path = write(tmp_path, r"nas_roots = ['\\NAS\Recordings\', '//nas/other/']")
    assert load_config(path).nas_roots == (r"\\NAS\Recordings", r"\\nas\other")


def test_unknown_keys_are_ignored(tmp_path):
    assert load_config(write(tmp_path, "colour = 'blue'\n[extra]\na = 1")) == Config()


def test_invalid_toml_names_the_file(tmp_path):
    path = write(tmp_path, "db_path = ")
    with pytest.raises(ConfigError, match="not valid TOML") as info:
        load_config(path)
    assert str(path) in str(info.value)


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("db_path = 3", "db_path"),
        ("db_path = ''", "db_path"),
        ("nas_roots = 'x'", "nas_roots"),
        ("nas_roots = [1]", "nas_roots"),
        ("nas_roots = ['D:\\\\data']", "nas_roots"),
        ("network_speed_mb_s = 'fast'", "network_speed_mb_s"),
        ("network_speed_mb_s = true", "network_speed_mb_s"),
        ("network_speed_mb_s = 0", "network_speed_mb_s"),
        ("network_speed_mb_s = nan", "network_speed_mb_s"),
        ("hash_sample_fraction = 0", "hash_sample_fraction"),
        ("hash_sample_fraction = 1.5", "hash_sample_fraction"),
        ("default_hash_mode = 'some'", "default_hash_mode"),
        ("storage_roots = 'x'", "storage_roots"),
        ("[storage_roots]\na = 1", "storage_roots"),
    ],
)
def test_wrong_value_names_the_file_and_key(tmp_path, text, key):
    path = write(tmp_path, text)
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert str(path) in str(info.value)
    assert key in str(info.value)


def test_file_that_is_not_utf8_is_an_error(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(b"db_path = '\xff'")
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(path)


def test_default_path_uses_appdata(tmp_path):
    path = default_config_path({"APPDATA": str(tmp_path)})
    assert path == tmp_path / "IQDataManager" / "config.toml"


def test_default_path_needs_appdata():
    with pytest.raises(ConfigError, match="APPDATA"):
        default_config_path({})


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (r"\\nas\recordings", True),
        (r"\\nas\recordings\iq", True),
        ("//nas/recordings", True),
        (r"\\nas", False),
        (r"\\?\C:\data", False),
        (r"\\.\C:", False),
        (r"D:\data", False),
        ("data", False),
    ],
)
def test_is_unc_path(text, expected):
    assert is_unc_path(text) is expected


def test_display_offset_defaults_to_8_hours(tmp_path):
    assert load_config(tmp_path / "absent.toml").display_utc_offset_hours == 8.0


@pytest.mark.parametrize(("text", "hours"), [("0", 0.0), ("5.5", 5.5), ("-3.75", -3.75)])
def test_display_offset_is_read(tmp_path, text, hours):
    path = write(tmp_path, f"display_utc_offset_hours = {text}")
    assert load_config(path).display_utc_offset_hours == hours


@pytest.mark.parametrize("text", ["15", "-13", "8.1", "'8'"])
def test_display_offset_must_be_a_real_offset(tmp_path, text):
    path = write(tmp_path, f"display_utc_offset_hours = {text}")
    with pytest.raises(ConfigError, match="display_utc_offset_hours"):
        load_config(path)
