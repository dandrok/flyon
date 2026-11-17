"""The notes contract: a transcript in, a `Note` out, with the provider named."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flyon.domain.note import Note
from flyon.domain.transcript import Transcript


class NotesError(RuntimeError):
    """Raised when a provider cannot be reached, refuses, or answers with something unusable."""


@runtime_checkable
class NotesProvider(Protocol):
    """Everything `flyon summarize` needs from a model.

    Interchangeable by construction: `tests/contract/test_notes.py` holds a scripted provider and
    the Ollama adapter (driven by a stub transport) to the same criteria, so a second backend —
    Gemini, a local llama.cpp — costs one line in that parametrization and one adapter.
    """

    @property
    def name(self) -> str:
        """Provider identity, written into the note's front-matter."""
        ...

    @property
    def model(self) -> str:
        """Model identity, same reason."""
        ...

    def summarize(self, transcript: Transcript) -> Note:
        """Read the whole transcript and return the note.

        An empty transcript raises `NotesError`: a note about nothing is a lie, and writing it would
        look like a meeting that happened.
        """
        ...
