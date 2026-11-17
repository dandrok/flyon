"""Wiring: configuration and flags turned into the adapters the CLI actually gets."""

from __future__ import annotations

from pathlib import Path

import pytest

from flyon.app.config import load_settings
from flyon.app.wiring import open_capturer, open_notes_provider, open_transcriber


@pytest.fixture()
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    return load_settings(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")


def test_the_language_flag_reaches_the_engine(settings: object) -> None:
    # AC-52: --language pl overrides the config for one meeting
    transcriber = open_transcriber(settings, "faster-whisper", "pl")  # type: ignore[arg-type]

    assert transcriber.language == "pl"


def test_without_a_flag_the_configured_language_is_used(settings: object) -> None:
    # AC-52
    transcriber = open_transcriber(settings)  # type: ignore[arg-type]

    assert transcriber.language is None  # empty config = detect once, then pin


def test_a_wav_source_needs_a_file(settings: object) -> None:
    # AC-51: a bare `wav:` is a typo, and says so before anything opens
    with pytest.raises(ValueError, match="needs a file"):
        open_capturer("wav:")


def test_an_unknown_source_lists_the_choices() -> None:
    with pytest.raises(ValueError, match="wav:<file>"):
        open_capturer("microphone")


def test_no_notes_provider_means_no_network_call(settings: object) -> None:
    # AC-48
    with pytest.raises(ValueError, match="no notes provider configured"):
        open_notes_provider(settings)  # type: ignore[arg-type]
