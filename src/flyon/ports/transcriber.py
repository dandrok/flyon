"""The transcription contract: PCM in, text out, with the engine's name attached."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from flyon.domain.pcm import SAMPLE_RATE


class TranscriberError(RuntimeError):
    """Raised when an engine cannot load or cannot decode a segment."""


@dataclass(frozen=True, slots=True)
class Transcription:
    """What one segment produced. `text` is stripped; empty means "no speech found"."""

    text: str
    engine: str
    model: str

    def __post_init__(self) -> None:
        if self.text != self.text.strip():
            raise ValueError("text must be stripped; whitespace is not a transcript")
        if not self.engine:
            raise ValueError("engine must be named: a transcript you cannot attribute is a guess")
        if not self.model:
            raise ValueError("model must be named")

    @property
    def is_empty(self) -> bool:
        return not self.text


@runtime_checkable
class Transcriber(Protocol):
    """What the session loop needs from a speech-to-text engine.

    Interchangeable by construction: `tests/contract/test_transcriber.py` holds a scripted engine
    and the `faster-whisper` adapter (driven by a stub model) to the same criteria, which is also
    how a second engine — whisper.cpp, Groq — gets tested without a download.
    """

    @property
    def name(self) -> str:
        """Engine identity, written into every line it produces."""
        ...

    @property
    def model(self) -> str:
        """Model identity, same reason."""
        ...

    def transcribe(self, pcm: bytes, *, sample_rate: int = SAMPLE_RATE) -> Transcription:
        """Decode one segment of `s16le` mono audio into text."""
        ...
