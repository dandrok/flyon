"""The notes port contract: a scripted provider and the Ollama adapter, one set of criteria.

A second backend — Gemini, a local llama.cpp — costs one line in `PROVIDERS` and one failing
adapter, not a second copy of these tests.
"""

from __future__ import annotations

import json
import urllib.error
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from flyon.adapters.notes.fake import FakeNotes
from flyon.adapters.notes.ollama import OllamaNotes
from flyon.domain.note import Note
from flyon.domain.segment import MIC, SYSTEM
from flyon.domain.transcript import Line, Transcript
from flyon.ports.notes import NotesError, NotesProvider

ANSWER = {
    "summary": "We agreed to keep the schema change and take the backfill.",
    "decisions": ["keep the schema change"],
    "action_items": ["take the backfill"],
    "open_questions": [],
}


def answered(url: str, body: Mapping[str, Any], timeout_s: float) -> Mapping[str, Any]:
    """A stand-in daemon: accepts anything, answers with a valid note."""
    return {"message": {"role": "assistant", "content": json.dumps(ANSWER)}}


def unreachable(url: str, body: Mapping[str, Any], timeout_s: float) -> Mapping[str, Any]:
    raise urllib.error.URLError("connection refused")


PROVIDERS: dict[str, Callable[[], NotesProvider]] = {
    "fake": lambda: FakeNotes(),
    "ollama": lambda: OllamaNotes("llama3.2", transport=answered),
}

FAILING: dict[str, Callable[[], NotesProvider]] = {
    "fake": lambda: FakeNotes(fail="the model refused"),
    "ollama": lambda: OllamaNotes("llama3.2", transport=unreachable),
}


@pytest.fixture(params=sorted(PROVIDERS), name="provider")
def provider_fixture(request: pytest.FixtureRequest) -> NotesProvider:
    return PROVIDERS[request.param]()


def transcript() -> Transcript:
    return Transcript(
        "6f4c",
        [
            Line(
                session_id="6f4c",
                stream=MIC,
                start_ms=0,
                end_ms=900,
                text="shall we start with the migration",
            ),
            Line(
                session_id="6f4c",
                stream=SYSTEM,
                start_ms=3_800,
                end_ms=4_700,
                text="the backfill is the only thing left",
            ),
        ],
    )


def test_every_provider_names_itself(provider: NotesProvider) -> None:
    # AC-44
    assert isinstance(provider, NotesProvider)
    assert provider.name.strip()
    assert provider.model.strip()


def test_every_provider_answers_with_a_note(provider: NotesProvider) -> None:
    # AC-44
    note = provider.summarize(transcript())

    assert isinstance(note, Note)
    assert note.summary.strip()
    assert all(item.strip() for item in note.decisions + note.actions + note.questions)


def test_no_provider_invents_a_note_from_nothing(provider: NotesProvider) -> None:
    # AC-44
    with pytest.raises(NotesError, match="no lines"):
        provider.summarize(Transcript("6f4c"))


@pytest.mark.parametrize("name", sorted(FAILING))
def test_a_provider_that_cannot_answer_raises_notes_error(name: str) -> None:
    # AC-44: one exception type, so the CLI has one path to report
    with pytest.raises(NotesError):
        FAILING[name]().summarize(transcript())
