"""The session loop: frames in, lines out.

This is the only place where capture, segmentation, transcription and storage meet. It holds the
ordering rules — one segmenter per stream, audio cut to the segment the level described, empty
transcriptions dropped, an engine failure survived — and none of the mechanisms: a fake capturer and
a fake engine run the whole loop in a test with no sound card and no model.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from flyon.domain.segment import Segment, Segmenter, SegmenterConfig
from flyon.domain.transcript import Line, Session, utcnow
from flyon.ports.capturer import Capturer, Frame
from flyon.ports.store import Store
from flyon.ports.transcriber import Transcriber, TranscriberError

LineHandler = Callable[[Line], None]
ErrorHandler = Callable[[str], None]


def new_session_id() -> str:
    """Short enough to type, long enough not to collide in a year of meetings."""
    return uuid4().hex[:12]


@dataclass(frozen=True, slots=True)
class SessionSummary:
    """What a finished session did, so the CLI can report rather than guess."""

    session: Session
    lines: tuple[Line, ...]
    segments: int
    empty_segments: int
    failed_segments: int


class SessionRecorder:
    """Drives one recording from `start()` to `finish()`."""

    def __init__(
        self,
        *,
        capturer: Capturer,
        transcriber: Transcriber,
        store: Store,
        session_id: str | None = None,
        title: str = "",
        segmenter_config: SegmenterConfig | None = None,
        on_line: LineHandler | None = None,
        on_error: ErrorHandler | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._capturer = capturer
        self._transcriber = transcriber
        self._store = store
        self._session_id = session_id or new_session_id()
        self._title = title
        self._config = segmenter_config or SegmenterConfig()
        self._on_line = on_line
        self._on_error = on_error
        self._clock = clock

    def run(self) -> SessionSummary:
        session = Session(session_id=self._session_id, started_at=self._clock(), title=self._title)
        self._store.create_session(session)

        segmenters = {stream: Segmenter(stream, self._config) for stream in self._capturer.streams}
        history: dict[str, deque[Frame]] = {stream: deque() for stream in segmenters}
        lines: list[Line] = []
        segments = empty = failed = 0

        def handle(segment: Segment) -> Line | None:
            nonlocal empty, failed
            audio = self._audio_for(history[segment.stream], segment)
            try:
                result = self._transcriber.transcribe(audio)
            except TranscriberError as exc:
                failed += 1
                self._report(f"{segment.stream} at {segment.start_ms}ms: {exc}")
                return None
            if result.is_empty:
                empty += 1
                return None
            line = self._store.append_line(
                Line(
                    session_id=session.session_id,
                    stream=segment.stream,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=result.text,
                    engine=result.engine,
                    model=result.model,
                )
            )
            if self._on_line is not None:
                self._on_line(line)
            return line

        self._capturer.start()
        try:
            for frame in self._capturer.frames():
                segmenter = segmenters.get(frame.stream)
                if segmenter is None:
                    continue
                window = history[frame.stream]
                window.append(frame)
                self._prune(window, self._config.max_segment_ms + frame.frame_ms)
                for segment in segmenter.push(frame.level, frame.frame_ms):
                    segments += 1
                    line = handle(segment)
                    if line is not None:
                        lines.append(line)
        except KeyboardInterrupt:
            # Ctrl-C finishes the recording instead of discarding it
            pass
        finally:
            self._capturer.stop()
            for segmenter in segmenters.values():
                for segment in segmenter.flush():
                    segments += 1
                    line = handle(segment)
                    if line is not None:
                        lines.append(line)
            self._store.end_session(session.session_id, self._clock())

        finished = self._store.get_session(session.session_id) or session
        return SessionSummary(
            session=finished,
            lines=tuple(lines),
            segments=segments,
            empty_segments=empty,
            failed_segments=failed,
        )

    def _audio_for(self, window: deque[Frame], segment: Segment) -> bytes:
        """The audio of exactly this segment — no leading or trailing silence padded in."""
        return b"".join(
            frame.pcm
            for frame in window
            if frame.at_ms >= segment.start_ms and frame.at_ms + frame.frame_ms <= segment.end_ms
        )

    @staticmethod
    def _prune(window: deque[Frame], keep_ms: int) -> None:
        """Drop audio older than the longest segment can be, so a meeting does not grow in RAM."""
        if not window:
            return
        newest = window[-1].at_ms + window[-1].frame_ms
        while window and window[0].at_ms + window[0].frame_ms <= newest - keep_ms:
            window.popleft()

    def _report(self, message: str) -> None:
        if self._on_error is not None:
            self._on_error(message)
