"""The Whisper adapter: conversion, laziness, one model instance, and the failure paths."""

from __future__ import annotations

import struct
import sys
from typing import Any

import pytest

from flyon.adapters.stt.faster_whisper import FasterWhisperTranscriber, to_float32
from flyon.ports.transcriber import TranscriberError


class Segment:
    def __init__(self, text: str) -> None:
        self.text = text


class StubModel:
    def __init__(self) -> None:
        self.calls = 0
        self.seen_lengths: list[int] = []

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[list[Segment], dict[str, Any]]:
        self.calls += 1
        self.seen_lengths.append(len(audio))
        return [Segment(" one "), Segment(" two ")], {}


def build(model: Any = None, **kwargs: Any) -> FasterWhisperTranscriber:
    stub = model or StubModel()
    return FasterWhisperTranscriber(model="tiny", model_factory=lambda: stub, **kwargs)


class LanguageStub:
    """A model that always reports the same detected language, and records what it was told."""

    def __init__(self, language: str = "pl", probability: float = 0.9) -> None:
        self.language = language
        self.probability = probability
        self.languages: list[str | None] = []

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[list[Segment], Any]:
        from types import SimpleNamespace

        self.languages.append(kwargs.get("language"))
        info = SimpleNamespace(language=self.language, language_probability=self.probability)
        return [Segment(" cue ")], info


def audio_of(seconds: float) -> bytes:
    return struct.pack(f"<{int(16_000 * seconds)}h", *([1000] * int(16_000 * seconds)))


def test_the_detected_language_is_pinned_once_enough_audio_has_been_heard() -> None:
    # AC-52: a 1.5 s segment is not enough evidence — Polish gets labelled Hungarian
    stub = LanguageStub("pl", 0.9)
    transcriber = build(stub)

    for _ in range(4):  # 6 s of audio, all detected as Polish
        transcriber.transcribe(audio_of(1.5))

    assert transcriber.language == "pl"
    transcriber.transcribe(audio_of(1.5))
    assert stub.languages == [None, None, None, None, "pl"]


def test_an_explicit_language_is_never_overridden_by_detection() -> None:
    # AC-52: the config wins, and no detection pass is needed
    stub = LanguageStub("pl", 0.99)
    transcriber = build(stub, language="en")

    for _ in range(4):
        transcriber.transcribe(audio_of(2.0))

    assert transcriber.language == "en"
    assert stub.languages == ["en"] * 4


def test_unconfident_short_audio_does_not_pin_a_language() -> None:
    # AC-52: guessing early is what produced the Hungarian transcript
    transcriber = build(LanguageStub("hu", 0.2), language_pin_after_s=6.0)

    transcriber.transcribe(audio_of(1.5))

    assert transcriber.language is None


def test_samples_are_scaled_to_float32() -> None:
    audio = to_float32(struct.pack("<2h", 16384, -16384))
    assert audio.dtype.name == "float32"
    assert audio[0] == pytest.approx(0.5, abs=0.001)
    assert audio[1] == pytest.approx(-0.5, abs=0.001)


def test_an_odd_trailing_byte_is_ignored_and_empty_audio_is_empty() -> None:
    assert len(to_float32(b"")) == 0
    assert len(to_float32(b"\x00")) == 0
    assert len(to_float32(struct.pack("<h", 100) + b"\x00")) == 1


def test_the_model_is_built_once_and_reused() -> None:
    stub = StubModel()
    transcriber = build(stub)
    assert not transcriber.loaded
    assert transcriber.transcribe(struct.pack("<320h", *([1000] * 320))).text == "one two"
    assert transcriber.loaded
    assert transcriber.transcribe(struct.pack("<320h", *([1000] * 320))).text == "one two"
    assert stub.calls == 2  # two segments decoded, one model instance


def test_empty_audio_never_touches_the_model() -> None:
    stub = StubModel()
    transcriber = build(stub)
    assert transcriber.transcribe(b"").is_empty
    assert stub.calls == 0
    assert not transcriber.loaded


def test_the_engine_name_and_model_are_written_into_the_result() -> None:
    result = build().transcribe(struct.pack("<320h", *([1000] * 320)))
    assert result.engine == "faster-whisper"
    assert result.model == "tiny"


def test_a_missing_extra_names_the_install_command(monkeypatch: pytest.MonkeyPatch) -> None:
    # a module set to None in sys.modules makes `import` raise ImportError, like an absent extra
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    transcriber = FasterWhisperTranscriber(model="tiny")
    with pytest.raises(TranscriberError, match="flyon\\[stt\\]"):
        transcriber.transcribe(struct.pack("<320h", *([1000] * 320)))


def test_a_model_that_will_not_load_says_which_model() -> None:
    def broken() -> StubModel:
        raise RuntimeError("no space left on device")

    transcriber = FasterWhisperTranscriber(model="large-v3-turbo", model_factory=broken)
    with pytest.raises(TranscriberError, match="large-v3-turbo"):
        transcriber.transcribe(struct.pack("<320h", *([1000] * 320)))


def test_a_decode_failure_becomes_a_transcriber_error() -> None:
    class Exploding(StubModel):
        def transcribe(self, audio: Any, **kwargs: Any) -> Any:
            raise RuntimeError("ctranslate2 exploded")

    transcriber = build(Exploding())
    with pytest.raises(TranscriberError, match="exploded"):
        transcriber.transcribe(struct.pack("<320h", *([1000] * 320)))
