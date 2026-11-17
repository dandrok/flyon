"""The capture contract: two streams, one timeline, frames with levels."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from flyon.domain.segment import STREAMS


class CapturerError(RuntimeError):
    """Raised when capture cannot start, or is asked to start twice."""


@dataclass(frozen=True, slots=True)
class Frame:
    """One 20 ms of one stream, with how loud it was."""

    stream: str
    level: float
    frame_ms: int
    at_ms: int

    def __post_init__(self) -> None:
        if self.stream not in STREAMS:
            raise ValueError(f"unknown stream {self.stream!r}; expected one of {STREAMS}")
        if not 0.0 <= self.level <= 1.0:
            raise ValueError(f"level must be in [0, 1], got {self.level}")
        if self.frame_ms <= 0:
            raise ValueError(f"frame_ms must be positive, got {self.frame_ms}")
        if self.at_ms < 0:
            raise ValueError(f"at_ms must not be negative, got {self.at_ms}")


@runtime_checkable
class Capturer(Protocol):
    """What the session loop needs from an audio source.

    Implementations must be interchangeable: `tests/contract/test_capturer.py` runs the same
    criteria against a scripted fake and the real `parec` adapter driven by a fake process.
    """

    def start(self) -> None:
        """Begin capturing. Idempotence is *not* promised: a second call raises `CapturerError`."""
        ...

    def stop(self) -> None:
        """Stop capturing and close every child process. Safe to call twice."""
        ...

    def frames(self) -> Iterator[Frame]:
        """Yield frames from every stream until stopped.

        One frame per `frame_ms` per stream, in arrival order. `at_ms` is the frame's offset in its
        own stream — both streams share a clock, so offsets are comparable across them.
        """
        ...
