"""End-to-end: one session written by a store, read back by the CLI.

No microphone and no model — this is the full loop that exists today, and the place the next slice
adds WAV fixtures to. Marked `slow` because it asserts over whole rendered output rather than units;
`make e2e` runs it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from flyon.adapters.store.jsonl import JsonlStore
from flyon.adapters.store.sqlite import SqliteStore
from flyon.cli.main import app
from flyon.domain.segment import MIC, SYSTEM
from flyon.domain.transcript import Line, Session
from flyon.ports.store import Store

pytestmark = pytest.mark.slow

RUNNER = CliRunner()
SESSION_ID = "6f4c1a2b9d8e"
UTTERANCES = [
    (0, MIC, "morning — shall we start with the migration?"),
    (1_200, SYSTEM, "yes, I pushed the schema change last night"),
    (3_800, MIC, "then the backfill is the only thing left"),
    (6_400, SYSTEM, "I can take that, it is maybe two days"),
]


def write_session(store: Store) -> None:
    started = datetime(2026, 11, 17, 10, 4, tzinfo=UTC)
    store.create_session(Session(session_id=SESSION_ID, started_at=started, title="weekly sync"))
    for start_ms, stream, text in UTTERANCES:
        store.append_line(
            Line(
                session_id=SESSION_ID,
                stream=stream,
                start_ms=start_ms,
                end_ms=start_ms + 900,
                text=text,
                engine="faster-whisper",
                model="large-v3-turbo",
            )
        )
    store.end_session(SESSION_ID, started + timedelta(minutes=12, seconds=31))


@pytest.mark.parametrize("backend", ["sqlite", "jsonl"])
def test_a_session_written_by_the_store_reads_back_through_the_cli(
    backend: str, tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    store: Store = (
        SqliteStore(data_dir / "flyon.db") if backend == "sqlite" else JsonlStore(data_dir)
    )
    write_session(store)
    store.close()

    config = tmp_path / "config.toml"
    config.write_text(f'store = "{backend}"\n', encoding="utf-8")

    listed = RUNNER.invoke(
        app, ["--config", str(config), "--data-dir", str(data_dir), "sessions", "--json"]
    )
    assert listed.exit_code == 0
    payload = json.loads(listed.stdout)
    assert payload["sessions"][0]["id"] == SESSION_ID
    assert payload["sessions"][0]["duration_ms"] == 12 * 60 * 1000 + 31 * 1000

    shown = RUNNER.invoke(
        app, ["--config", str(config), "--data-dir", str(data_dir), "show", "6f4c"]
    )
    assert shown.exit_code == 0
    assert [line.split(maxsplit=2)[2] for line in shown.stdout.splitlines()[1:]] == [
        text for _, _, text in UTTERANCES
    ]
    assert "00:06 system" in shown.stdout
