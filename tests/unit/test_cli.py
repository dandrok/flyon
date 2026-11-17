"""The CLI as a user types it — AC-18 … AC-25 and AC-JSON of spec.md."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flyon import __version__
from flyon.adapters.store.jsonl import JsonlStore
from flyon.adapters.store.sqlite import SqliteStore
from flyon.cli.main import app
from flyon.domain.segment import MIC, SYSTEM
from flyon.domain.transcript import Line, Session

RUNNER = CliRunner()
SESSION_ID = "6f4c1a2b9d8e"


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "data"
    directory.mkdir()
    return directory


def invoke(*args: str) -> Any:
    return RUNNER.invoke(app, list(args))


def seed(data_dir: Path, *, lines: int = 2, open_session: bool = False) -> str:
    started = datetime(2026, 11, 17, 10, 4, tzinfo=UTC)
    store = SqliteStore(data_dir / "flyon.db")
    try:
        store.create_session(
            Session(session_id=SESSION_ID, started_at=started, title="weekly sync")
        )
        for index in range(lines):
            store.append_line(
                Line(
                    session_id=SESSION_ID,
                    stream=MIC if index % 2 == 0 else SYSTEM,
                    start_ms=index * 1_000,
                    end_ms=index * 1_000 + 800,
                    text=f"line {index}",
                    engine="faster-whisper",
                    model="large-v3-turbo",
                )
            )
        if not open_session:
            store.end_session(SESSION_ID, started + timedelta(minutes=12))
    finally:
        store.close()
    return SESSION_ID


def test_the_version_prints_and_exits_zero() -> None:
    # AC-18
    result = invoke("--version")
    assert result.exit_code == 0
    assert result.stdout.strip() == f"flyon {__version__}"


def test_the_bare_command_answers_without_a_dashboard(data_dir: Path) -> None:
    # AC-19
    result = invoke("--data-dir", str(data_dir))
    assert result.exit_code == 0
    assert "no sessions yet" in result.stdout
    assert len(result.stdout.strip().splitlines()) == 2


def test_the_bare_command_summarises_the_latest_session(data_dir: Path) -> None:
    seed(data_dir)
    result = invoke("--data-dir", str(data_dir))
    assert result.exit_code == 0
    assert SESSION_ID[:8] in result.stdout
    assert len(result.stdout.strip().splitlines()) == 2


def test_sessions_json_is_pure_json(data_dir: Path) -> None:
    # AC-20 + AC-JSON
    seed(data_dir)
    result = invoke("--data-dir", str(data_dir), "sessions", "--json")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sessions"][0]["id"] == SESSION_ID
    assert payload["sessions"][0]["lines"] == 2
    assert payload["sessions"][0]["duration_ms"] == 12 * 60 * 1000
    assert result.stderr == ""


def test_sessions_json_on_an_empty_directory_is_an_empty_list(data_dir: Path) -> None:
    # AC-24: a fresh --data-dir never leaks the default one
    result = invoke("--data-dir", str(data_dir), "sessions", "--json")
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"sessions": []}


def test_sessions_without_json_prints_a_table(data_dir: Path) -> None:
    seed(data_dir)
    result = invoke("--data-dir", str(data_dir), "sessions")
    assert result.exit_code == 0
    assert SESSION_ID[:8] in result.stdout
    assert "weekly sync" in result.stdout


def test_show_resolves_a_unique_prefix_and_renders_timestamps(data_dir: Path) -> None:
    # AC-21
    seed(data_dir)
    result = invoke("--data-dir", str(data_dir), "show", "6f4c")
    assert result.exit_code == 0
    assert "00:00" in result.stdout
    assert "00:01" in result.stdout
    assert "line 0" in result.stdout


def test_show_json_is_pure_json(data_dir: Path) -> None:
    # AC-21 + AC-JSON
    seed(data_dir)
    result = invoke("--data-dir", str(data_dir), "show", "6f4c", "--json")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session"]["id"] == SESSION_ID
    assert [line["text"] for line in payload["lines"]] == ["line 0", "line 1"]
    assert payload["lines"][1]["stream"] == SYSTEM
    assert result.stderr == ""


def test_show_with_an_unknown_prefix_fails_and_says_so_on_stderr(data_dir: Path) -> None:
    # AC-22
    seed(data_dir)
    result = invoke("--data-dir", str(data_dir), "show", "dead")
    assert result.exit_code == 1
    assert "no session matches" in result.stderr
    assert result.stdout == ""


def test_show_with_an_ambiguous_prefix_lists_the_candidates(data_dir: Path) -> None:
    seed(data_dir)
    store = SqliteStore(data_dir / "flyon.db")
    store.create_session(
        Session(
            session_id="6f4c999999",
            started_at=datetime(2026, 11, 17, 12, 0, tzinfo=UTC),
        )
    )
    store.close()
    result = invoke("--data-dir", str(data_dir), "show", "6f4c")
    assert result.exit_code == 1
    assert "2 sessions match" in result.stderr


def test_the_configured_store_backend_is_the_one_the_cli_reads(tmp_path: Path) -> None:
    # AC-26: the backend is configuration, not an import buried in the CLI
    data_dir = tmp_path / "data"
    store = JsonlStore(data_dir)
    store.create_session(
        Session(
            session_id=SESSION_ID,
            started_at=datetime(2026, 11, 17, 10, 4, tzinfo=UTC),
            title="weekly sync",
        )
    )
    store.append_line(
        Line(session_id=SESSION_ID, stream=MIC, start_ms=0, end_ms=500, text="line 0")
    )
    store.close()
    config = tmp_path / "config.toml"
    config.write_text('store = "jsonl"\n', encoding="utf-8")
    result = invoke("--config", str(config), "--data-dir", str(data_dir), "sessions", "--json")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["sessions"][0]["id"] == SESSION_ID
    assert payload["sessions"][0]["lines"] == 1


def test_the_bare_command_with_no_sessions_mentions_the_next_step(data_dir: Path) -> None:
    result = invoke("--data-dir", str(data_dir))
    assert "doctor" in result.stdout


def test_doctor_reports_every_check_and_succeeds_when_nothing_failed(tmp_path: Path) -> None:
    # AC-23: a missing STT extra or capture tool is a warning, not a failure
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    result = invoke("--data-dir", str(data_dir), "--cache-dir", str(cache_dir), "doctor")
    assert result.exit_code == 0
    for name in ("python", "data dir", "config", "store", "stt extra", "capture", "models"):
        assert name in result.stdout
    assert "warn" in result.stdout


def test_doctor_names_the_default_model_and_its_download_size(tmp_path: Path) -> None:
    # AC-42: a warning about a download is only useful with a number in it
    result = invoke(
        "--data-dir", str(tmp_path / "data"), "--cache-dir", str(tmp_path / "cache"), "doctor"
    )
    assert "small" in result.stdout
    assert "464 MB" in result.stdout


def test_doctor_probe_reports_frames_per_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-27: the probe is a real capture, so the CLI is tested with a scripted capturer behind it
    from flyon.adapters.capture.fake import FakeCapturer
    from flyon.cli import doctor as doctor_module

    script = [("mic", 0.3)] * 5 + [("system", 0.0)] * 5
    monkeypatch.setattr(doctor_module, "_real_capturer", lambda: FakeCapturer(script))
    result = invoke(
        "--data-dir",
        str(tmp_path / "d"),
        "--cache-dir",
        str(tmp_path / "c"),
        "doctor",
        "--probe",
        "--seconds",
        "0.2",
    )
    assert result.exit_code == 0
    assert "probe mic" in result.stdout
    assert "probe system" in result.stdout
    assert "5 frames" in result.stdout


def test_doctor_probe_without_a_capturer_fails_loudly() -> None:
    from flyon.cli import doctor as doctor_module
    from flyon.ports.capturer import CapturerError

    class Broken:
        def start(self) -> None:
            raise CapturerError("parec: not found")

        def stop(self) -> None:
            pass

        def frames(self):  # type: ignore[no-untyped-def]
            return iter(())

    checks = doctor_module.probe_capture(capturer=Broken(), seconds=0.1)  # type: ignore[arg-type]
    assert checks[0].status == "fail"
    assert "not found" in checks[0].detail


def test_a_data_dir_that_cannot_be_a_database_exits_two_without_a_traceback(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    result = invoke("--data-dir", str(blocked), "sessions")
    assert result.exit_code == 2
    assert "cannot open the store" in result.stderr
    assert "Traceback" not in result.stderr


def test_doctor_exits_one_when_a_directory_is_unusable(tmp_path: Path) -> None:
    # AC-23: a real failure is a red row and a non-zero exit, not a warning
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    result = invoke("--data-dir", str(tmp_path / "data"), "--cache-dir", str(blocked), "doctor")
    assert result.exit_code == 1
    assert "FAIL" in result.stdout
    assert "cache dir" in result.stdout


def test_a_broken_config_exits_two_without_a_traceback(tmp_path: Path) -> None:
    # AC-25
    config = tmp_path / "config.toml"
    config.write_text("model = [unclosed\n", encoding="utf-8")
    result = invoke("--config", str(config), "sessions")
    assert result.exit_code == 2
    assert "config.toml" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_named_but_missing_config_exits_two(tmp_path: Path) -> None:
    result = invoke("--config", str(tmp_path / "ghost.toml"), "sessions")
    assert result.exit_code == 2
    assert "no such config file" in result.stderr


def test_help_lists_every_command() -> None:
    result = invoke("--help")
    assert result.exit_code == 0
    for command in ("sessions", "show", "doctor"):
        assert command in result.stdout
