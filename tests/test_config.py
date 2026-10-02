"""Tests for iqdm.config. Every configuration file lives in tmp_path."""

from pathlib import Path

import pytest

from iqdm import config as config_module
from iqdm.config import (
    Config,
    ConfigError,
    SettingsInput,
    backup_path,
    default_config_path,
    hidden_key_error,
    is_unc_path,
    load_config,
    merge_settings,
    read_config_data,
    save_config,
    settings_errors,
    settings_from_data,
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


# =========================================================================
# Writing (Settings tab, Milestone 3a)
# =========================================================================

FULL_FILE = r"""# a comment that Save loses
db_path = 'D:\data\catalog.db'
network_speed_mb_s = 95
colour = 'blue'
nas_roots = ['\\nas\recordings']
display_utc_offset_hours = 5.5
logged_at = 2026-09-30T08:15:00Z

[storage_roots]
'\\nas\recordings' = '/mnt/nas/recordings'

[extra.nested]
a = [1, 2]
"""


def test_read_config_data_of_a_missing_file_is_empty(tmp_path):
    assert read_config_data(tmp_path / "absent.toml") == {}


def test_read_config_data_is_unchecked(tmp_path):
    data = read_config_data(write(tmp_path, "network_speed_mb_s = -1\ncolour = 'blue'"))
    assert data == {"network_speed_mb_s": -1, "colour": "blue"}


def test_read_config_data_refuses_invalid_toml(tmp_path):
    with pytest.raises(ConfigError, match="not valid TOML"):
        read_config_data(write(tmp_path, "db_path = "))


def test_settings_from_data_takes_the_shown_keys(tmp_path):
    settings = settings_from_data(read_config_data(write(tmp_path, FULL_FILE)))
    assert settings == SettingsInput(
        db_path=r"D:\data\catalog.db",
        nas_roots=(r"\\nas\recordings",),
        display_utc_offset_hours=5.5,
    )


def test_settings_from_data_keeps_a_wrong_root_as_typed():
    settings = settings_from_data({"nas_roots": [r"D:\data", 3], "db_path": 7})
    assert settings.nas_roots == (r"D:\data",)
    assert settings.db_path == ""


@pytest.mark.parametrize("offset", ["8", True, [8]])
def test_settings_from_data_gives_the_default_offset_for_a_wrong_type(offset):
    assert settings_from_data({"display_utc_offset_hours": offset}).display_utc_offset_hours == 8.0


def test_settings_errors_accept_valid_input():
    settings = SettingsInput(
        db_path="", nas_roots=(r"\\nas\rec", r" \\nas\rec2\ "), display_utc_offset_hours=-3.75
    )
    assert settings_errors(settings) == {}


@pytest.mark.parametrize("root", [r"D:\data", r"\\?\C:\data", r"\\.\C:", r"\\nas", ""])
def test_settings_errors_refuse_a_root_that_is_not_unc(root):
    errors = settings_errors(SettingsInput(nas_roots=(r"\\nas\rec", root)))
    assert list(errors) == ["nas_roots"]
    assert "not a UNC path" in errors["nas_roots"]


@pytest.mark.parametrize("hours", [-12.0, 14.0, 5.75, 0.0])
def test_settings_errors_accept_offset_limits(hours):
    assert settings_errors(SettingsInput(display_utc_offset_hours=hours)) == {}


@pytest.mark.parametrize("hours", [-12.25, 14.25, 5.1])
def test_settings_errors_refuse_a_wrong_offset(hours):
    errors = settings_errors(SettingsInput(display_utc_offset_hours=hours))
    assert list(errors) == ["display_utc_offset_hours"]


def test_hidden_key_error_ignores_the_shown_keys():
    data = {"nas_roots": ["D:\\data"], "display_utc_offset_hours": 99, "db_path": 3}
    assert hidden_key_error(data, "config.toml") is None


def test_hidden_key_error_names_the_key():
    error = hidden_key_error({"network_speed_mb_s": -1}, "config.toml")
    assert error is not None
    assert "network_speed_mb_s" in error


def test_merge_keeps_every_key_that_is_not_shown(tmp_path):
    data = read_config_data(write(tmp_path, FULL_FILE))
    merged = merge_settings(data, SettingsInput(db_path=r"E:\new.db"))
    assert merged["colour"] == "blue"
    assert merged["network_speed_mb_s"] == 95
    assert merged["storage_roots"] == {r"\\nas\recordings": "/mnt/nas/recordings"}
    assert merged["extra"] == {"nested": {"a": [1, 2]}}
    assert merged["logged_at"] == data["logged_at"]
    assert merged["db_path"] == r"E:\new.db"
    assert data["db_path"] == r"D:\data\catalog.db"  # the input is not changed


def test_merge_removes_a_blank_db_path():
    merged = merge_settings({"db_path": r"D:\a.db"}, SettingsInput(db_path="   "))
    assert "db_path" not in merged


def test_merge_cleans_nas_roots():
    merged = merge_settings({}, SettingsInput(nas_roots=(r" \\nas\rec\ ", "//nas/other/")))
    assert merged["nas_roots"] == [r"\\nas\rec", r"\\nas\other"]


@pytest.mark.parametrize(("hours", "written"), [(8.0, 8), (-3.0, -3), (5.5, 5.5), (0.0, 0)])
def test_merge_writes_whole_hours_as_an_integer(hours, written):
    merged = merge_settings({}, SettingsInput(display_utc_offset_hours=hours))
    assert merged["display_utc_offset_hours"] == written
    assert type(merged["display_utc_offset_hours"]) is type(written)


def test_save_creates_a_missing_folder(tmp_path):
    path = tmp_path / "AppData" / "IQDataManager" / "config.toml"
    save_config(path, {"db_path": r"D:\a.db"})
    assert load_config(path).db_path == r"D:\a.db"


def test_save_reads_back_the_same_config(tmp_path):
    path = write(tmp_path, FULL_FILE)
    settings = SettingsInput(
        db_path=r"\\nas\recordings\iq_catalog.db",
        nas_roots=(r"\\nas\recordings", r"\\nas2\Récordings é"),
        display_utc_offset_hours=-9.5,
    )
    returned = save_config(path, merge_settings(read_config_data(path), settings))
    loaded = load_config(path)
    assert loaded == returned
    assert loaded.db_path == r"\\nas\recordings\iq_catalog.db"
    assert loaded.nas_roots == (r"\\nas\recordings", r"\\nas2\Récordings é")
    assert loaded.display_utc_offset_hours == -9.5
    assert loaded.network_speed_mb_s == 95.0
    assert read_config_data(path)["extra"] == {"nested": {"a": [1, 2]}}


def test_save_loses_comments(tmp_path):
    path = write(tmp_path, FULL_FILE)
    save_config(path, read_config_data(path))
    assert "a comment" not in path.read_text(encoding="utf-8")


def test_first_save_writes_no_backup(tmp_path):
    path = tmp_path / "config.toml"
    save_config(path, {})
    assert path.exists()
    assert not backup_path(path).exists()
    assert not (tmp_path / "config.toml.new").exists()


def test_each_save_replaces_the_backup_with_the_previous_file(tmp_path):
    path = write(tmp_path, FULL_FILE)
    assert backup_path(path) == tmp_path / "config.toml.bak"
    save_config(path, {"db_path": r"D:\first.db"})
    assert backup_path(path).read_text(encoding="utf-8") == FULL_FILE
    first = path.read_bytes()
    save_config(path, {"db_path": r"D:\second.db"})
    assert backup_path(path).read_bytes() == first
    assert load_config(path).db_path == r"D:\second.db"


def test_save_overwrites_a_leftover_new_file(tmp_path):
    path = tmp_path / "config.toml"
    (tmp_path / "config.toml.new").write_text("left over", encoding="utf-8")
    save_config(path, {"db_path": r"D:\a.db"})
    assert load_config(path).db_path == r"D:\a.db"
    assert not (tmp_path / "config.toml.new").exists()


def test_save_refuses_a_wrong_value_and_writes_nothing(tmp_path):
    path = write(tmp_path, FULL_FILE)
    with pytest.raises(ConfigError, match="network_speed_mb_s"):
        save_config(path, {"network_speed_mb_s": -1})
    assert path.read_text(encoding="utf-8") == FULL_FILE
    assert not backup_path(path).exists()
    assert not (tmp_path / "config.toml.new").exists()


def test_failed_replace_leaves_the_old_file(tmp_path, monkeypatch):
    path = write(tmp_path, FULL_FILE)
    before = path.read_bytes()

    def fail(self, target):
        raise PermissionError("file in use")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(ConfigError, match="cannot write the file"):
        save_config(path, {"db_path": r"D:\a.db"})
    assert path.read_bytes() == before


def test_failed_serialising_leaves_the_old_file(tmp_path, monkeypatch):
    path = write(tmp_path, FULL_FILE)
    before = path.read_bytes()

    def fail(data):
        raise TypeError("cannot serialise")

    monkeypatch.setattr(config_module.tomli_w, "dumps", fail)
    with pytest.raises(ConfigError, match="cannot write the value"):
        save_config(path, {"db_path": r"D:\a.db"})
    assert path.read_bytes() == before
    assert not (tmp_path / "config.toml.new").exists()


def test_save_over_an_unreadable_file_keeps_it_as_backup(tmp_path):
    path = write(tmp_path, "db_path = ")
    before = path.read_bytes()
    save_config(path, merge_settings({}, SettingsInput(db_path=r"D:\a.db")))
    assert load_config(path).db_path == r"D:\a.db"
    assert backup_path(path).read_bytes() == before
