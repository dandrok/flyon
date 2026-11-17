"""Rendering, writing and orchestrating a note: front-matter, sections, atomic files."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from flyon.adapters.notes.fake import FakeNotes
from flyon.adapters.store.jsonl import JsonlStore
from flyon.app.notes import note_path, render_note, summarize_session, write_note
from flyon.domain.note import Note
from flyon.domain.segment import MIC, SYSTEM
from flyon.domain.transcript import Line, Session, Transcript
from flyon.ports.notes import NotesError

SESSION_ID = "6f4c1a2b9d8e"
STARTED = datetime(2026, 11, 17, 10, 4, tzinfo=UTC)


def session(title: str = "weekly sync") -> Session:
    return Session(
        session_id=SESSION_ID,
        started_at=STARTED,
        ended_at=STARTED + timedelta(minutes=12, seconds=31),
        title=title,
    )


def transcript() -> Transcript:
    return Transcript(
        SESSION_ID,
        [
            Line(
                session_id=SESSION_ID,
                stream=MIC,
                start_ms=0,
                end_ms=900,
                text="shall we start with the migration",
            ),
            Line(
                session_id=SESSION_ID,
                stream=SYSTEM,
                start_ms=3_800,
                end_ms=4_700,
                text="the backfill is the only thing left",
            ),
        ],
    )


def note() -> Note:
    return Note(
        summary="We agreed to keep the schema change.",
        decisions=("keep the schema change",),
        actions=("take the backfill",),
        questions=(),
    )


def test_the_note_opens_with_front_matter_a_tool_can_read() -> None:
    # AC-46
    text = render_note(note(), session(), transcript())

    assert text.startswith("---\n")
    assert f"session: {SESSION_ID}" in text
    assert "duration: 12:31" in text
    assert "streams: mic, system" in text
    assert "lines: 2" in text
    assert text.count("---\n") >= 2


def test_the_four_sections_are_always_there_and_empty_ones_say_so() -> None:
    # AC-46: a missing section reads as "not asked", "- none" reads as "nothing"
    text = render_note(note(), session(), transcript())

    for heading in ("## Summary", "## Decisions", "## Action items", "## Open questions"):
        assert heading in text
    assert "- take the backfill" in text
    assert text.count("- none") == 1


def test_an_untitled_session_still_gets_a_heading() -> None:
    # AC-46
    assert "# Meeting" in render_note(note(), session(title=""), transcript())


def test_writing_is_atomic_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    # AC-47
    target = tmp_path / "notes" / f"{SESSION_ID}.md"

    write_note("first\n", target)
    write_note("second\n", target)

    assert target.read_text(encoding="utf-8") == "second\n"
    assert [path.name for path in target.parent.iterdir()] == [target.name]


def test_a_write_that_cannot_start_leaves_nothing_behind(tmp_path: Path) -> None:
    # AC-47: the failure mode that matters is a half-written note looking finished
    blocker = tmp_path / "notes"
    blocker.write_text("not a directory", encoding="utf-8")

    with pytest.raises(OSError):
        write_note("text\n", blocker / f"{SESSION_ID}.md")

    assert blocker.read_text(encoding="utf-8") == "not a directory"
    assert list(tmp_path.iterdir()) == [blocker]


def test_a_note_lands_in_the_data_dir_and_nowhere_else(tmp_path: Path) -> None:
    # AC-46
    store = JsonlStore(tmp_path / "data")
    store.create_session(session())
    for line in transcript().lines:
        store.append_line(line)

    result = summarize_session(
        store=store, provider=FakeNotes(), session=session(), data_dir=tmp_path / "data"
    )

    assert result.path == note_path(tmp_path / "data", SESSION_ID)
    assert result.path.is_file()
    assert result.copy_path is None
    assert "## Summary" in result.path.read_text(encoding="utf-8")
    assert result.provider == "fake"
    assert result.model == "scripted"
    store.close()


def test_the_extra_copy_is_identical_bytes(tmp_path: Path) -> None:
    # AC-49
    store = JsonlStore(tmp_path / "data")
    store.create_session(session())
    for line in transcript().lines:
        store.append_line(line)
    vault = tmp_path / "vault" / "Meetings"

    result = summarize_session(
        store=store,
        provider=FakeNotes(),
        session=session(),
        data_dir=tmp_path / "data",
        extra_copy=vault,
    )

    assert result.copy_path == vault / f"{SESSION_ID}.md"
    assert result.copy_path.read_bytes() == result.path.read_bytes()
    store.close()


def test_a_provider_that_fails_leaves_no_note_behind(tmp_path: Path) -> None:
    # AC-47
    store = JsonlStore(tmp_path / "data")
    store.create_session(session())
    for line in transcript().lines:
        store.append_line(line)

    with pytest.raises(NotesError, match="ollama is down"):
        summarize_session(
            store=store,
            provider=FakeNotes(fail="ollama is down"),
            session=session(),
            data_dir=tmp_path / "data",
        )

    assert not note_path(tmp_path / "data", SESSION_ID).exists()
    store.close()


def test_an_open_session_can_still_be_summarised(tmp_path: Path) -> None:
    # AC-46: a session interrupted mid-meeting is still worth minutes
    open_session = Session(session_id=SESSION_ID, started_at=STARTED, title="still going")
    store = JsonlStore(tmp_path / "data")
    store.create_session(open_session)
    for line in transcript().lines:
        store.append_line(line)

    result = summarize_session(
        store=store, provider=FakeNotes(), session=open_session, data_dir=tmp_path / "data"
    )

    assert "duration: unknown" in result.path.read_text(encoding="utf-8")
    store.close()
