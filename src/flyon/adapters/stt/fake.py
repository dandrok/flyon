"""A scripted transcriber: deterministic text, no model, no download.

Two jobs: the contract test needs an engine that never varies, and `flyon listen --engine fake`
lets the whole pipeline run on a machine where a model download is not welcome (CI, a fresh box).
"""

from __future__ import annotations

from collections.abc import Sequence

from flyon.domain.pcm import SAMPLE_RATE, rms_level
from flyon.ports.transcriber import TranscriberError, Transcription

DEFAULT_WORDS: tuple[str, ...] = ("hello", "this", "is", "a", "demo")


class FakeTranscriber:
    """Satisfies `Transcriber`. Silence gives no text; anything louder gives scripted words."""

    name = "fake"

    def __init__(
        self,
        model: str = "scripted",
        words: Sequence[str] = DEFAULT_WORDS,
        threshold: float = 0.01,
        fail_on_empty_audio: bool = False,
    ) -> None:
        self._model = model
        self._words = tuple(words)
        self._threshold = threshold
        self._fail_on_empty = fail_on_empty_audio
        self.calls: list[int] = []

    @property
    def model(self) -> str:
        return self._model

    def transcribe(self, pcm: bytes, *, sample_rate: int = SAMPLE_RATE) -> Transcription:
        if not pcm:
            if self._fail_on_empty:
                raise TranscriberError("no audio to transcribe")
            return Transcription(text="", engine=self.name, model=self._model)
        self.calls.append(len(pcm))
        if rms_level(pcm) < self._threshold:
            return Transcription(text="", engine=self.name, model=self._model)
        return Transcription(text=" ".join(self._words), engine=self.name, model=self._model)
