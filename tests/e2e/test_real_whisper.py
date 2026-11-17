"""The real engine, a real model, real speech — the last unknown in M2.

Everything else in the suite drives `FasterWhisperTranscriber` with a stub model: that proves the
shape of the adapter, not that `ctranslate2` decodes speech on this machine. This file is the one
place a model is actually downloaded and actually listened to.

`slow`, so `make check` never touches it, and skipped when the `stt` extra is absent. The model is
cached in the same directory `flyon listen` uses (`platformdirs`' cache dir), so running the tests
once means the first recording does not download anything. It runs against the shipped default
(`DEFAULT_MODEL`), because a verification test for a model nobody ships verifies nothing:

    make e2e                                        # the shipped default, 464 MB
    FLYON_TEST_WHISPER_MODEL=tiny make e2e            # 75 MB, quicker, worse text
    FLYON_TEST_WHISPER_MODEL=large-v3-turbo make e2e   # the read-it-afterwards model, 1.6 GB
"""

from __future__ import annotations

import importlib.util
import os
import time
import wave
from pathlib import Path

import numpy as np
import pytest

from flyon.adapters.stt.faster_whisper import DEFAULT_MODEL, FasterWhisperTranscriber
from flyon.app.config import default_cache_dir
from flyon.domain.pcm import SAMPLE_RATE

HAS_STT = importlib.util.find_spec("faster_whisper") is not None

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not HAS_STT, reason="needs the stt extra: uv sync --extra stt"),
]

FIXTURES = Path(__file__).parent.parent / "fixtures" / "speech"
SPEECH = FIXTURES / "start-with-the-migration.16k.wav"
MODEL = os.environ.get("FLYON_TEST_WHISPER_MODEL", DEFAULT_MODEL)


def pcm_of(path: Path, *, limit_ms: int | None = None) -> bytes:
    """The fixture is committed as the same `s16le` mono 16 kHz bytes `parec` delivers."""
    with wave.open(str(path), "rb") as handle:
        assert handle.getnchannels() == 1, "the pipeline is mono"
        assert handle.getsampwidth() == 2, "the pipeline is s16le"
        assert handle.getframerate() == SAMPLE_RATE
        frames = handle.getnframes()
        if limit_ms is not None:
            frames = min(frames, SAMPLE_RATE * limit_ms // 1000)
        return handle.readframes(frames)


def transcriber(model: str = MODEL) -> FasterWhisperTranscriber:
    return FasterWhisperTranscriber(model=model, cache_dir=default_cache_dir())


def test_a_real_model_transcribes_real_speech() -> None:
    """AC-41: the words come back, and they are attributed to the engine that produced them."""
    audio = pcm_of(SPEECH)
    seconds = len(audio) / (SAMPLE_RATE * 2)
    engine = transcriber()

    started = time.perf_counter()
    engine.transcribe(audio)  # the first call pays for the model load
    cold = time.perf_counter() - started

    started = time.perf_counter()
    result = engine.transcribe(audio)
    warm = time.perf_counter() - started
    print(
        f"\n{MODEL}: {seconds:.2f}s of audio — first call {cold:.2f}s (load included), "
        f"second {warm:.2f}s ({warm / seconds:.2f}x realtime)"
    )

    text = result.text.lower()
    assert "start" in text
    assert "migration" in text
    assert result.engine == "faster-whisper"
    assert result.model == MODEL


def test_a_segment_length_clip_still_produces_text() -> None:
    """AC-41: our segments are short — silence closes them, 15 s caps them — so 1.5 s must work.

    The words degrade at this length (a clipped word is a different word), which is why this
    asserts text arrives rather than which text: the exact wording is the first test's job.
    """
    audio = pcm_of(SPEECH, limit_ms=1_500)

    result = transcriber().transcribe(audio)

    assert not result.is_empty
    assert result.engine == "faster-whisper"


def test_the_whole_loop_runs_from_a_wav_file(tmp_path: Path) -> None:
    """AC-51: capture, segment, transcribe and store with no microphone and no sound card.

    This is the test that separates "the pipeline is broken" from "your device is not delivering
    audio" — the two look identical from the outside, and only one of them is flyon's problem.
    """
    from typer.testing import CliRunner

    from flyon.cli.main import app

    result = CliRunner().invoke(
        app,
        [
            "--data-dir",
            str(tmp_path / "data"),
            "listen",
            "--source",
            f"wav:{SPEECH}",
            "--title",
            "wav fixture",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert "migration" in result.stdout.lower()
    assert "1 lines" in result.stdout


def test_digital_silence_produces_no_text() -> None:
    """AC-41: a silent segment must not invent a sentence, or the transcript fills with ghosts.

    This is the one that caught a real hallucination: without `vad_filter`, `small` answers `"You"`
    to digital silence. With it, every model measured returns nothing.
    """
    silence = bytes(SAMPLE_RATE * 2 * 2)  # two seconds of s16le zeros

    result = transcriber().transcribe(silence)

    assert result.text == ""
    assert result.model == MODEL


def test_loud_non_speech_produces_no_text() -> None:
    """AC-41: noise loud enough to clear the voice gate must not become a line either."""
    rng = np.random.default_rng(7)
    samples = (rng.uniform(-1, 1, SAMPLE_RATE * 2) * 0.05 * 32_767).astype("<i2")

    result = transcriber().transcribe(samples.tobytes())

    assert result.text == ""
