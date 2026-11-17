"""`flyon listen` end to end with the scripted source and engine — no microphone, no model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flyon.cli.main import app

RUNNER = CliRunner()


def listen(*args: str) -> Any:
    return RUNNER.invoke(app, list(args))


def test_listen_records_a_scripted_conversation_and_reports_it(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    result = listen(
        "--data-dir",
        str(data_dir),
        "listen",
        "--source",
        "fake",
        "--engine",
        "fake",
        "--title",
        "scripted sync",
    )
    assert result.exit_code == 0
    assert "recording mic, system" in result.stdout
    assert "hello this is a demo" in result.stdout
    assert "2 lines" in result.stdout

    listed = listen("--data-dir", str(data_dir), "sessions", "--json")
    payload = json.loads(listed.stdout)
    assert payload["sessions"][0]["title"] == "scripted sync"
    assert payload["sessions"][0]["lines"] == 2
    assert payload["sessions"][0]["ended_at"] is not None


def test_the_recorded_lines_are_readable_by_show(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    listen("--data-dir", str(data_dir), "listen", "--source", "fake", "--engine", "fake")
    session_id = json.loads(listen("--data-dir", str(data_dir), "sessions", "--json").stdout)[
        "sessions"
    ][0]["id"]
    shown = listen("--data-dir", str(data_dir), "show", session_id[:8])
    assert shown.exit_code == 0
    assert "00:00 mic" in shown.stdout
    assert "hello this is a demo" in shown.stdout


def test_quiet_records_without_printing_the_transcript(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    result = listen(
        "--data-dir", str(data_dir), "listen", "--source", "fake", "--engine", "fake", "--quiet"
    )
    assert result.exit_code == 0
    assert "hello this is a demo" not in result.stdout
    assert "2 lines" in result.stdout


def test_an_unknown_source_is_a_clean_error(tmp_path: Path) -> None:
    result = listen("--data-dir", str(tmp_path / "d"), "listen", "--source", "microphone")
    assert result.exit_code == 2
    assert "unknown capture source" in result.stderr


def test_an_unknown_engine_is_a_clean_error(tmp_path: Path) -> None:
    result = listen(
        "--data-dir", str(tmp_path / "d"), "listen", "--source", "fake", "--engine", "gpt"
    )
    assert result.exit_code == 2
    assert "unknown engine" in result.stderr


def test_a_missing_stt_extra_says_how_to_install_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    monkeypatch.setitem(sys.modules, "numpy", None)
    result = listen("--data-dir", str(tmp_path / "d"), "listen")
    assert result.exit_code == 2
    assert "flyon[stt]" in result.stderr
