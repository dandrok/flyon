"""A scripted capturer: no audio, no processes, same contract.

Used by the contract test, and by `flyon listen --source fake` when someone wants to see the
pipeline run on a machine with no microphone (a CI runner, for instance).
"""

from __future__ import annotations

import struct
from collections.abc import Iterator, Mapping, Sequence

from flyon.domain.pcm import FRAME_MS, bytes_per_frame
from flyon.ports.capturer import CapturerError, Frame

SPEECH_FRAMES = 20  # 400 ms — above the 250 ms minimum segment
SILENCE_FRAMES = 45  # 900 ms — above the 800 ms silence threshold, so it closes a segment


def _default_script() -> tuple[tuple[str, float], ...]:
    """Two short turns: the microphone speaks, then the system does, then both fall silent."""
    return (
        *((("mic", 0.5),) * SPEECH_FRAMES),
        *((("mic", 0.0),) * SILENCE_FRAMES),
        *((("system", 0.0),) * SPEECH_FRAMES),
        *((("system", 0.6),) * SPEECH_FRAMES),
        *((("system", 0.0),) * SILENCE_FRAMES),
    )


DEFAULT_SCRIPT: tuple[tuple[str, float], ...] = _default_script()


def synthesize_pcm(level: float, frame_ms: int = FRAME_MS) -> bytes:
    """Audio whose measured level is exactly `level` — a constant sample, i.e. a square wave."""
    clipped = max(0.0, min(1.0, level))
    samples = bytes_per_frame(frame_ms) // 2
    return struct.pack(f"<{samples}h", *([int(clipped * 32767)] * samples))


class FakeCapturer:
    """Yields a fixed list of `(stream, level)` pairs, one frame each. Satisfies `Capturer`."""

    def __init__(
        self, script: Sequence[tuple[str, float]] = DEFAULT_SCRIPT, *, frame_ms: int = FRAME_MS
    ) -> None:
        self._script = tuple(script)
        self._frame_ms = frame_ms
        self._started = False
        self._stopped = False

    @property
    def streams(self) -> Mapping[str, str]:
        names = dict.fromkeys(stream for stream, _level in self._script)
        return {stream: f"scripted {stream}" for stream in names}

    def start(self) -> None:
        if self._started:
            raise CapturerError("already started")
        self._started = True

    def stop(self) -> None:
        self._stopped = True

    def frames(self) -> Iterator[Frame]:
        if not self._started:
            raise CapturerError("start() before frames()")
        offsets: dict[str, int] = {}
        for stream, level in self._script:
            if self._stopped:
                return
            at_ms = offsets.get(stream, 0)
            offsets[stream] = at_ms + self._frame_ms
            yield Frame(
                stream=stream,
                level=level,
                frame_ms=self._frame_ms,
                at_ms=at_ms,
                pcm=synthesize_pcm(level, self._frame_ms),
            )
