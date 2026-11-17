"""A scripted notes provider: fixed text, no daemon, no network.

Two jobs, the same two the scripted transcriber has: the contract test needs a provider that never
varies, and `flyon summarize --provider fake` proves the whole path — prompt, note file,
front-matter, extra copy — on a machine with no model running.
"""

from __future__ import annotations

from flyon.domain.note import Note
from flyon.domain.transcript import Transcript
from flyon.ports.notes import NotesError

SCRIPTED = Note(
    summary=(
        "The team reviewed the migration and agreed to keep the schema change as pushed. "
        "The backfill is the only remaining piece of work."
    ),
    decisions=("the schema change stays as pushed",),
    actions=("take the backfill, about two days",),
    questions=("anything else before the demo on Friday?",),
)


class FakeNotes:
    """Satisfies `NotesProvider`. Returns a fixed note, or fails on demand."""

    name = "fake"

    def __init__(self, note: Note = SCRIPTED, *, fail: str = "") -> None:
        self._note = note
        self._fail = fail if fail else None

    @property
    def model(self) -> str:
        return "scripted"

    def summarize(self, transcript: Transcript) -> Note:
        if self._fail is not None:
            raise NotesError(self._fail)
        if not transcript.lines:
            raise NotesError("nothing to summarise: the session has no lines")
        return self._note
