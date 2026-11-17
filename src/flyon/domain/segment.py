"""Segmenter: fixed frames in, speech segments out.

Pure arithmetic. The caller owns the clock and pushes one level per frame; this module decides
where a segment starts, where it ends, and when a monologue must be cut. Nothing here touches audio,
a database, or the wall clock, which is why every rule below is testable in microseconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

MIC: Final = "mic"
SYSTEM: Final = "system"
STREAMS: Final[tuple[str, ...]] = (MIC, SYSTEM)
STREAM_ORDER: Final[dict[str, int]] = {MIC: 0, SYSTEM: 1}


@dataclass(frozen=True, slots=True)
class Segment:
    """A stretch of speech on one stream, in milliseconds from the session start."""

    stream: str
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.stream not in STREAMS:
            raise ValueError(f"unknown stream {self.stream!r}; expected one of {STREAMS}")
        if self.start_ms < 0:
            raise ValueError(f"start_ms must not be negative, got {self.start_ms}")
        if self.end_ms < self.start_ms:
            raise ValueError(f"end_ms {self.end_ms} is before start_ms {self.start_ms}")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True, slots=True)
class SegmenterConfig:
    """Thresholds that decide where a segment ends."""

    voice_threshold: float = 0.02
    silence_ms: int = 800
    max_segment_ms: int = 15_000
    min_segment_ms: int = 250
    frame_ms: int = 20

    def __post_init__(self) -> None:
        if not 0.0 < self.voice_threshold <= 1.0:
            raise ValueError(f"voice_threshold must be in (0, 1], got {self.voice_threshold}")
        if self.silence_ms <= 0:
            raise ValueError(f"silence_ms must be positive, got {self.silence_ms}")
        if self.min_segment_ms < 0:
            raise ValueError(f"min_segment_ms must not be negative, got {self.min_segment_ms}")
        if self.max_segment_ms < max(self.min_segment_ms, 1_000):
            raise ValueError(
                f"max_segment_ms {self.max_segment_ms} is too small for "
                f"min_segment_ms {self.min_segment_ms}"
            )
        if self.frame_ms <= 0:
            raise ValueError(f"frame_ms must be positive, got {self.frame_ms}")


class Segmenter:
    """One segmenter per stream.

    Silence closes a segment at its last voiced frame; a segment still open at
    ``max_segment_ms`` is force-cut there and the next voiced frame opens a new one, so a long
    monologue becomes a sequence of timestamped segments with no audio lost between them.
    """

    def __init__(self, stream: str, config: SegmenterConfig | None = None) -> None:
        if stream not in STREAMS:
            raise ValueError(f"unknown stream {stream!r}; expected one of {STREAMS}")
        self._stream = stream
        self._config = config if config is not None else SegmenterConfig()
        self._now_ms = 0
        self._start_ms: int | None = None
        self._last_voice_end_ms = 0
        self._silence_ms = 0

    @property
    def stream(self) -> str:
        return self._stream

    @property
    def config(self) -> SegmenterConfig:
        return self._config

    @property
    def is_open(self) -> bool:
        return self._start_ms is not None

    def push(self, level: float, frame_ms: int | None = None) -> tuple[Segment, ...]:
        """Feed one frame's level; return every segment this frame closed."""
        step = self._config.frame_ms if frame_ms is None else frame_ms
        if step <= 0:
            raise ValueError(f"frame_ms must be positive, got {step}")

        closed: list[Segment] = []
        start = self._now_ms
        end = start + step
        self._now_ms = end

        if level >= self._config.voice_threshold:
            if self._start_ms is None:
                self._start_ms = start
            self._last_voice_end_ms = end
            self._silence_ms = 0
            if end - self._start_ms >= self._config.max_segment_ms:
                segment = self._close(end)
                if segment is not None:
                    closed.append(segment)
        elif self._start_ms is not None:
            self._silence_ms += step
            if self._silence_ms >= self._config.silence_ms:
                segment = self._close(self._last_voice_end_ms)
                if segment is not None:
                    closed.append(segment)

        return tuple(closed)

    def flush(self) -> tuple[Segment, ...]:
        """Close a segment that is still open — stopping mid-sentence keeps the tail."""
        if self._start_ms is None:
            return ()
        segment = self._close(self._last_voice_end_ms)
        return () if segment is None else (segment,)

    def _close(self, end_ms: int) -> Segment | None:
        if self._start_ms is None:
            return None
        start_ms = self._start_ms
        self._start_ms = None
        self._silence_ms = 0
        segment = Segment(self._stream, start_ms, end_ms)
        if segment.duration_ms < self._config.min_segment_ms:
            return None
        return segment
