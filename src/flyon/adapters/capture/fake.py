"""A scripted capturer: no audio, no processes, same contract.

Used by the contract test, and by `flyon listen --source fake` when someone wants to see the
pipeline run on a machine with no microphone (a CI runner, for instance).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from flyon.domain.pcm import FRAME_MS
from flyon.ports.capturer import CapturerError, Frame

DEFAULT_SCRIPT: tuple[tuple[str, float], ...] = (
    ("mic", 0.0),
    ("mic", 0.4),
    ("mic", 0.5),
    ("system", 0.0),
    ("system", 0.6),
    ("mic", 0.0),
)


class FakeCapturer:
    """Yields a fixed list of `(stream, level)` pairs, one frame each. Satisfies `Capturer`."""

    def __init__(
        self, script: Sequence[tuple[str, float]] = DEFAULT_SCRIPT, *, frame_ms: int = FRAME_MS
    ) -> None:
        self._script = tuple(script)
        self._frame_ms = frame_ms
        self._started = False
        self._stopped = False

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
            yield Frame(stream=stream, level=level, frame_ms=self._frame_ms, at_ms=at_ms)
