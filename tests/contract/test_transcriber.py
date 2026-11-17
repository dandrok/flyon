"""One transcription contract, two engines.

A scripted engine and the `faster-whisper` adapter driven by a stub model: same criteria, no
download. A third engine joins this parametrization and inherits the whole check list.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

import pytest

from flyon.adapters.stt.fake import FakeTranscriber
from flyon.adapters.stt.faster_whisper import FasterWhisperTranscriber
from flyon.ports.transcriber import Transcriber, Transcription


@dataclass
class StubSegment:
    text: str


class StubModel:
    """The two attributes of `WhisperModel` this adapter touches."""

    def __init__(self, words: tuple[str, ...] = ("stub", "engine", "text")) -> None:
        self.words = words
        self.calls = 0

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[list[StubSegment], dict[str, Any]]:
        self.calls += 1
        if len(audio) == 0 or float(abs(audio).max()) < 1e-6:
            return [], {"language": "en"}  # what a real model does with silence
        return [StubSegment(" " + word + " ") for word in self.words], {"language": "en"}


def pcm(samples: int, amplitude: float = 0.0) -> bytes:
    value = int(amplitude * 32767)
    return struct.pack(f"<{samples}h", *([value] * samples))


@pytest.fixture(params=["fake", "faster-whisper"])
def transcriber(request: pytest.FixtureRequest) -> Transcriber:
    if request.param == "fake":
        return FakeTranscriber()
    return FasterWhisperTranscriber(model="stub-small", model_factory=StubModel)


def test_speech_produces_named_attributed_text(transcriber: Transcriber) -> None:
    result = transcriber.transcribe(pcm(320, 0.5))
    assert isinstance(result, Transcription)
    assert result.text
    assert result.engine == transcriber.name
    assert result.model == transcriber.model
    assert not result.is_empty


def test_text_is_stripped_so_whitespace_never_becomes_a_line(transcriber: Transcriber) -> None:
    result = transcriber.transcribe(pcm(320, 0.5))
    assert result.text == result.text.strip()


def test_silence_produces_no_text(transcriber: Transcriber) -> None:
    result = transcriber.transcribe(pcm(320, 0.0))
    assert result.is_empty


def test_empty_audio_is_not_an_exception(transcriber: Transcriber) -> None:
    result = transcriber.transcribe(b"")
    assert result.is_empty
    assert result.engine == transcriber.name


def test_the_engine_and_model_survive_autodetect_language(transcriber: Transcriber) -> None:
    assert transcriber.name in {"fake", "faster-whisper"}
    assert transcriber.model


def test_an_empty_transcription_is_refused_by_the_type_itself() -> None:
    with pytest.raises(ValueError, match="engine must be named"):
        Transcription(text="hello", engine="", model="m")
    with pytest.raises(ValueError, match="stripped"):
        Transcription(text=" hello", engine="fake", model="m")
