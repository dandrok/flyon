"""Local Whisper through CTranslate2 — the default engine, imported lazily.

`faster-whisper` lives in the `flyon[stt]` extra. Importing it here would cost every command a heavy
import chain, so the module is loaded on first use and a missing extra becomes one clear error
instead of an ImportError from three frames deep.
"""

from __future__ import annotations

import array
import threading
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from flyon.domain.pcm import SAMPLE_RATE, SAMPLE_WIDTH
from flyon.ports.transcriber import TranscriberError, Transcription

# `small`, not the most accurate model: a call pays a whole 30 s encoder window and the pipeline
# makes one call per segment. `large-v3-turbo` spends ~7 s on a 5 s segment, so it cannot keep up
# with a normal turn-taking pace on CPU. `small` answers in ~1.7 s, exact on clean speech.
# Numbers: docs/VERIFICATION.md. Decision: docs/adr/005.
DEFAULT_MODEL = "small"

# Measured downloads, so `doctor` warns with a real number or admits it does not know one.
MODEL_DOWNLOAD_SIZES = {
    "tiny": "75 MB",
    "base": "142 MB",
    "small": "464 MB",
    "large-v3-turbo": "1.6 GB",
}
INSTALL_HINT = "uv tool install 'flyon[stt]'"

ModelFactory = Callable[[], "Any"]


def _import_faster_whisper() -> ModuleType:
    try:
        # deliberately lazy: a heavy import must not be paid by `flyon sessions`
        import faster_whisper
    except ImportError as exc:  # pragma: no cover - exercised on a machine without the extra
        raise TranscriberError(f"faster-whisper is not installed — {INSTALL_HINT}") from exc
    return faster_whisper


def to_float32(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> Any:
    """`s16le` bytes -> mono float32 in -1.0 … 1.0, which is what Whisper wants.

    numpy is imported here rather than at module level: it arrives with `ctranslate2`, so it is
    present whenever this adapter can actually run, and absent on every path that cannot.
    """
    import numpy as np

    usable = len(pcm) - len(pcm) % SAMPLE_WIDTH
    if usable <= 0:
        return np.zeros(0, dtype=np.float32)
    samples = array.array("h")
    samples.frombytes(pcm[:usable])
    audio = np.asarray(samples, dtype=np.float32) / 32_768.0
    return audio


class FasterWhisperTranscriber:
    """Satisfies `Transcriber`. One model instance, loaded once, reused across segments.

    `vad_filter` is on by default: the Silero VAD inside faster-whisper drops non-speech before the
    decoder runs, which is the difference between a silent segment and the word `"You"` invented out
    of it (measured: `docs/VERIFICATION.md`). It also costs less than decoding silence, so it pays
    for itself on the quiet stretches of a meeting.
    """

    name = "faster-whisper"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        cache_dir: Path | None = None,
        language: str = "",
        beam_size: int = 5,
        compute_type: str = "int8",
        device: str = "cpu",
        vad_filter: bool = True,
        model_factory: ModelFactory | None = None,
        language_pin_after_s: float = 6.0,
    ) -> None:
        self._model_name = model
        self._cache_dir = cache_dir
        self._language = language or None
        self._beam_size = beam_size
        self._compute_type = compute_type
        self._device = device
        self._vad_filter = vad_filter
        self._factory = model_factory
        self._pin_after_s = language_pin_after_s
        self._votes: dict[str, float] = {}
        self._heard_s = 0.0
        self._pinned: str | None = None
        self._instance: Any | None = None
        self._lock = threading.Lock()

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def loaded(self) -> bool:
        return self._instance is not None

    def transcribe(self, pcm: bytes, *, sample_rate: int = SAMPLE_RATE) -> Transcription:
        if not pcm:
            return Transcription(text="", engine=self.name, model=self._model_name)
        audio = to_float32(pcm, sample_rate)
        seconds = len(pcm) / (sample_rate * SAMPLE_WIDTH)
        try:
            segments, info = self._engine().transcribe(
                audio,
                language=self._language or self._pinned,
                beam_size=self._beam_size,
                vad_filter=self._vad_filter,
                condition_on_previous_text=False,
            )
            text = " ".join(getattr(segment, "text", "").strip() for segment in segments).strip()
        except Exception as exc:  # any engine failure is one failure here
            raise TranscriberError(f"{self._model_name} failed: {exc}") from exc
        self._learn_language(info, seconds)
        return Transcription(text=text, engine=self.name, model=self._model_name)

    def _learn_language(self, info: Any, seconds: float) -> None:
        """Decide the session's language once, from the evidence heard so far.

        Whisper detects a language per call from that call's audio, and a 1.5 s segment is not
        enough evidence: Polish in short bursts comes back labelled Hungarian and transliterated. So
        detections are votes weighted by audio length and confidence, the winner is pinned once
        enough audio has arrived, and every later call is decoded as that language — which is also
        cheaper, because the detection pass stops happening.
        """
        if self._language is not None or self._pinned is not None:
            return
        detected = getattr(info, "language", None)
        if not detected:
            return
        probability = float(getattr(info, "language_probability", 0.0) or 0.0)
        self._votes[str(detected)] = self._votes.get(str(detected), 0.0) + seconds * max(
            probability, 0.1
        )
        self._heard_s += seconds
        if self._heard_s >= self._pin_after_s:
            self._pinned = max(self._votes, key=lambda name: self._votes[name])

    @property
    def language(self) -> str | None:
        """What the engine is decoding as: configured, pinned, or still undecided."""
        return self._language or self._pinned

    def _engine(self) -> Any:
        with self._lock:
            if self._instance is None:
                self._instance = self._build()
            return self._instance

    def _build(self) -> Any:
        if self._factory is not None:
            return self._factory()
        faster_whisper = _import_faster_whisper()
        model_kwargs: dict[str, Any] = {
            "device": self._device,
            "compute_type": self._compute_type,
        }
        if self._cache_dir is not None:
            model_kwargs["download_root"] = str(self._cache_dir)
        try:
            return faster_whisper.WhisperModel(self._model_name, **model_kwargs)
        except Exception as exc:  # a failed download or a CTranslate2 failure
            raise TranscriberError(f"cannot load {self._model_name}: {exc}") from exc
