"""Sessions, lines and the append-only transcript they form."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from flyon.domain.segment import STREAM_ORDER, STREAMS


class OutOfOrderLine(ValueError):
    """Raised when a line would break the transcript's append-only order."""


def utcnow() -> datetime:
    """The clock, in one place, so a test can pin it."""
    return datetime.now(tz=UTC)


def format_timestamp(ms: int) -> str:
    """Render milliseconds as ``mm:ss``, or ``h:mm:ss`` past an hour."""
    if ms < 0:
        raise ValueError(f"cannot format a negative timestamp: {ms}")
    total_seconds = ms // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


@dataclass(frozen=True, slots=True)
class Line:
    """One recognised utterance, on one stream."""

    session_id: str
    stream: str
    start_ms: int
    end_ms: int
    text: str
    engine: str = "unknown"
    model: str = "unknown"
    line_id: int | None = None

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

    @property
    def timestamp(self) -> str:
        return format_timestamp(self.start_ms)


@dataclass(frozen=True, slots=True)
class Session:
    """One meeting: when it started, when it stopped, and what to call it."""

    session_id: str
    started_at: datetime
    ended_at: datetime | None = None
    title: str = ""

    @property
    def is_open(self) -> bool:
        return self.ended_at is None

    @property
    def duration_ms(self) -> int | None:
        if self.ended_at is None:
            return None
        return int((self.ended_at - self.started_at).total_seconds() * 1000)


class Transcript:
    """An append-only, ordered collection of lines for one session."""

    def __init__(self, session_id: str, lines: Iterable[Line] = ()) -> None:
        self._session_id = session_id
        self._lines: list[Line] = []
        for line in lines:
            self.append(line)

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def lines(self) -> tuple[Line, ...]:
        return tuple(self._lines)

    def append(self, line: Line) -> Line:
        if line.session_id != self._session_id:
            raise ValueError(
                f"line belongs to session {line.session_id!r}, "
                f"this transcript is {self._session_id!r}"
            )
        if self._lines and line.start_ms < self._lines[-1].start_ms:
            raise OutOfOrderLine(
                f"line at {line.start_ms} ms arrives after one at {self._lines[-1].start_ms} ms"
            )
        self._lines.append(line)
        return line

    def extend(self, lines: Iterable[Line]) -> None:
        for line in lines:
            self.append(line)

    def text(self) -> str:
        return "\n".join(line.text for line in self._lines)

    def __len__(self) -> int:
        return len(self._lines)


def sort_lines(lines: Iterable[Line]) -> tuple[Line, ...]:
    """Order lines by start time, microphone first when two start together."""
    return tuple(sorted(lines, key=lambda line: (line.start_ms, STREAM_ORDER[line.stream])))
