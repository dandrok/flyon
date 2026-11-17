"""A WAV file as the microphone: the whole pipeline with no sound card and no Bluetooth.

Why this exists: the live loop's failure mode on a real machine is *silence*, and silence is hard to
debug through a headset that suspends, a profile that switches, or a mic that delivers zeros. A file
has none of those properties. `flyon listen --source wav:speech.wav` runs capture, segmentation,
transcription and the store over known audio, so "the pipeline is broken" and "your microphone is
broken" stop looking the same.

The system stream is silence on purpose: a fixture is one voice, and inventing the other side of a
meeting that never happened would make the test a lie.
"""

from __future__ import annotations

import wave
from collections.abc import Iterator, Mapping
from pathlib import Path

from flyon.domain.pcm import FRAME_MS, SAMPLE_RATE, SAMPLE_WIDTH, bytes_per_frame, rms_level
from flyon.domain.segment import MIC, SYSTEM
from flyon.ports.capturer import CapturerError, Frame

CONVERT_HINT = "convert it first: ffmpeg -i <file> -ar 16000 -ac 1 -c:a pcm_s16le speech.wav"


class WavCapturer:
    """Satisfies `Capturer`. Replays a 16 kHz mono `s16le` WAV on the microphone stream."""

    def __init__(self, path: Path, *, frame_ms: int = FRAME_MS) -> None:
        self._path = path.expanduser()
        self._frame_ms = frame_ms
        self._frame_bytes = bytes_per_frame(frame_ms)
        self._frame_samples = self._frame_bytes // SAMPLE_WIDTH
        self._started = False
        self._stopped = False

    @property
    def streams(self) -> Mapping[str, str]:
        return {MIC: f"{self._path.name} (wav)", SYSTEM: "silence"}

    def start(self) -> None:
        if self._started:
            raise CapturerError("already started")
        self._check_format()
        self._started = True

    def stop(self) -> None:
        self._stopped = True

    def frames(self) -> Iterator[Frame]:
        if not self._started:
            raise CapturerError("start() before frames()")
        with wave.open(str(self._path), "rb") as handle:
            offset = 0
            while not self._stopped:
                data = handle.readframes(self._frame_samples)
                if not data:
                    return
                if len(data) < self._frame_bytes:
                    data += bytes(self._frame_bytes - len(data))
                yield Frame(
                    stream=MIC,
                    level=rms_level(data),
                    frame_ms=self._frame_ms,
                    at_ms=offset,
                    pcm=data,
                )
                yield Frame(
                    stream=SYSTEM,
                    level=0.0,
                    frame_ms=self._frame_ms,
                    at_ms=offset,
                    pcm=bytes(self._frame_bytes),
                )
                offset += self._frame_ms

    def _check_format(self) -> None:
        """Refuse early and precisely: a wrong WAV is a one-line ffmpeg command, not a mystery."""
        try:
            with wave.open(str(self._path), "rb") as handle:
                channels = handle.getnchannels()
                width = handle.getsampwidth()
                rate = handle.getframerate()
        except (OSError, EOFError, wave.Error) as exc:
            raise CapturerError(f"cannot read {self._path}: {exc}") from exc
        if (rate, channels, width) != (SAMPLE_RATE, 1, SAMPLE_WIDTH):
            raise CapturerError(
                f"{self._path} is {rate} Hz, {channels} channel(s), "
                f"{width * 8}-bit — a capture WAV must be {SAMPLE_RATE} Hz, mono, 16-bit PCM; "
                f"{CONVERT_HINT}"
            )
