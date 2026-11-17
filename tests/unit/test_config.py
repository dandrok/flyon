"""Configuration: defaults, TOML overrides, and the failures a user will actually hit."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from flyon.app.config import SettingsError, load_settings


def test_defaults_come_from_platformdirs_and_the_decided_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    settings = load_settings()
    assert settings.data_dir == tmp_path / "xdg-data" / "flyon"
    assert settings.cache_dir == tmp_path / "xdg-cache" / "flyon"
    assert settings.config_path == tmp_path / "xdg-config" / "flyon" / "config.toml"
    assert settings.model == "large-v3-turbo"
    assert settings.engine == "faster-whisper"
    assert settings.config_found is False
    assert settings.segmenter.max_segment_ms == 15_000


def test_a_config_file_overrides_the_defaults(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        'model = "small"\nlanguage = "pl"\n\n'
        "[segmenter]\nsilence_ms = 1200\nmax_segment_ms = 20000\n\n"
        '[output]\nextra_copy = "~/notes/meetings"\n',
        encoding="utf-8",
    )
    settings = load_settings(config=config, data_dir=tmp_path / "d", cache_dir=tmp_path / "c")
    assert settings.config_found is True
    assert settings.model == "small"
    assert settings.language == "pl"
    assert settings.segmenter.silence_ms == 1200
    assert settings.segmenter.to_domain().max_segment_ms == 20_000
    assert settings.output.extra_copy_path() == Path("~/notes/meetings").expanduser()


def test_flags_win_over_the_platformdirs_defaults(tmp_path: Path) -> None:
    settings = load_settings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    assert settings.data_dir == tmp_path / "data"
    assert settings.cache_dir == tmp_path / "cache"


def test_the_cli_flag_beats_the_config_file(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(f'data_dir = "{tmp_path / "from-config"}"\n', encoding="utf-8")
    settings = load_settings(config=config, data_dir=tmp_path / "from-flag")
    assert settings.data_dir == tmp_path / "from-flag"


def test_a_named_config_file_that_does_not_exist_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="no such config file"):
        load_settings(config=tmp_path / "ghost.toml")


def test_a_broken_config_file_names_the_file(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("model = [unclosed\n", encoding="utf-8")
    with pytest.raises(SettingsError, match=re.escape("config.toml")):
        load_settings(config=config)


def test_an_invalid_threshold_is_rejected_with_the_field_name(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[segmenter]\nsilence_ms = 0\n", encoding="utf-8")
    with pytest.raises(SettingsError, match="silence_ms"):
        load_settings(config=config)


def test_an_unknown_key_is_rejected_rather_than_ignored(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[segmenter]\nsilence_ms = 900\nsilence = 900\n", encoding="utf-8")
    with pytest.raises(SettingsError, match="silence"):
        load_settings(config=config)
