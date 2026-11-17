"""The session loop: frames in, lines out — with a scripted capturer and a scripted engine."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from flyon.adapters.capture.fake import FakeCapturer
from flyon.adapters.store.sqlite import SqliteStore
from flyon.adapters.stt.fake import FakeTranscriber
from flyon.app.session import SessionRecorder
from flyon.domain.pcm import FRAME_MS
from flyon.domain.segment import MIC, SYSTEM, Segment
from flyon.ports.capturer import CapturerError, Frame
from flyon.ports.store import Store
from flyon.ports.transcriber import TranscriberError, Transcription

T0 = datetime(2026, 11, 17, 10, 4, tzinfo=UTC)


def clock() -> datetime:
    """A clock that moves a second per call, so `started_at` and `ended_at` differ."""
    clock.calls += 1  # type: ignore[attr-defined]
    return T0 + timedelta(seconds=clock.calls)


clock.calls = 0  # type: ignore[attr-defined]


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    made = SqliteStore(tmp_path / "flyon.db")
    yield made
    made.close()


def speech_script() -> list[tuple[str, float]]:
    return [
        *((MIC, 0.5),) * 20,
        *((MIC, 0.0),) * 45,
        *((SYSTEM, 0.0),) * 20,
        *((SYSTEM, 0.6),) * 20,
        *((SYSTEM, 0.0),) * 45,
    ]


class RecordingTranscriber(FakeTranscriber):
    """FakeTranscriber that remembers the audio it was handed."""

    def __init__(self) -> None:
        super().__init__()
        self.audio: list[bytes] = []

    def transcribe(self, pcm: bytes, *, sample_rate: int = 16_000) -> Transcription:
        self.audio.append(pcm)
        return super().transcribe(pcm, sample_rate=sample_rate)


def recorder(
    store: Store, capturer: FakeCapturer, transcriber: object | None = None, **kwargs: object
) -> SessionRecorder:
    return SessionRecorder(
        capturer=capturer,
        transcriber=transcriber or FakeTranscriber(),  # type: ignore[arg-type]
        store=store,
        clock=clock,
        **kwargs,  # type: ignore[arg-type]
    )


def test_a_scripted_conversation_becomes_two_attributed_lines(store: Store) -> None:
    summary = recorder(store, FakeCapturer(speech_script())).run()
    assert [line.stream for line in summary.lines] == [MIC, SYSTEM]
    assert [line.text for line in summary.lines] == ["hello this is a demo", "hello this is a demo"]
    assert all(line.engine == "fake" for line in summary.lines)
    assert all(line.model == "scripted" for line in summary.lines)
    assert summary.segments == 2
    assert summary.empty_segments == 0


def test_the_session_is_created_and_finished(store: Store) -> None:
    summary = recorder(store, FakeCapturer(speech_script())).run()
    stored = store.get_session(summary.session.session_id)
    assert stored is not None
    assert not stored.is_open
    assert stored.duration_ms is not None and stored.duration_ms >= 1_000
    assert [line.text for line in store.lines(stored.session_id)] == [
        "hello this is a demo",
        "hello this is a demo",
    ]


def test_the_audio_handed_to_the_engine_is_the_segment_not_the_silence(store: Store) -> None:
    transcriber = RecordingTranscriber()
    summary = recorder(store, FakeCapturer(speech_script()), transcriber).run()
    first = transcriber.audio[0]
    # 400 ms of speech at 20 ms per frame, and no trailing silence padded in
    assert len(first) == 20 * 640
    assert summary.lines[0].end_ms - summary.lines[0].start_ms == 400


def test_silence_only_produces_no_lines_but_still_closes_the_session(store: Store) -> None:
    script = [(MIC, 0.0)] * 100 + [(SYSTEM, 0.0)] * 100
    summary = recorder(store, FakeCapturer(script)).run()
    assert summary.lines == ()
    assert summary.segments == 0
    assert not (store.get_session(summary.session.session_id) or summary.session).is_open


def test_an_empty_transcription_is_counted_not_stored(store: Store) -> None:
    class Mute(FakeTranscriber):
        def transcribe(self, pcm: bytes, *, sample_rate: int = 16_000) -> Transcription:
            return Transcription(text="", engine="fake", model="scripted")

    summary = recorder(store, FakeCapturer(speech_script()), Mute()).run()
    assert summary.lines == ()
    assert summary.empty_segments == 2
    assert store.line_count(summary.session.session_id) == 0


def test_an_engine_failure_does_not_end_the_recording(store: Store) -> None:
    class Flaky(FakeTranscriber):
        def __init__(self) -> None:
            super().__init__()
            self.seen = 0

        def transcribe(self, pcm: bytes, *, sample_rate: int = 16_000) -> Transcription:
            self.seen += 1
            if self.seen == 1:
                raise TranscriberError("model unloaded")
            return super().transcribe(pcm, sample_rate=sample_rate)

    errors: list[str] = []
    summary = recorder(store, FakeCapturer(speech_script()), Flaky(), on_error=errors.append).run()
    assert summary.failed_segments == 1
    assert len(summary.lines) == 1  # the second segment still landed
    assert errors and "model unloaded" in errors[0]
    assert not (store.get_session(summary.session.session_id) or summary.session).is_open


def test_each_line_is_reported_as_it_arrives(store: Store) -> None:
    seen = []
    recorder(store, FakeCapturer(speech_script()), on_line=seen.append).run()
    assert [line.text for line in seen] == ["hello this is a demo", "hello this is a demo"]


def test_ctrl_c_finishes_the_session_instead_of_discarding_it(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "flyon.db")

    class Interrupting(FakeCapturer):
        def frames(self) -> Iterator[Frame]:
            for index, frame in enumerate(super().frames()):
                if index == 10:
                    raise KeyboardInterrupt
                yield frame

    summary = recorder(store, Interrupting()).run()
    stored = store.get_session(summary.session.session_id)
    assert stored is not None
    assert not stored.is_open  # finalised, not abandoned
    store.close()


def test_a_frame_from_a_stream_the_capturer_never_declared_is_ignored(store: Store) -> None:
    class MicOnly(FakeCapturer):
        @property
        def streams(self) -> dict[str, str]:
            return {MIC: "scripted mic"}

    summary = recorder(store, MicOnly(speech_script())).run()
    assert {line.stream for line in summary.lines} == {MIC}
    assert summary.segments == 1  # the system frames never reached a segmenter


def test_the_audio_window_is_pruned_so_a_meeting_does_not_grow_in_memory() -> None:
    from collections import deque

    window: deque[Frame] = deque(
        Frame(stream=MIC, level=0.0, frame_ms=FRAME_MS, at_ms=index * FRAME_MS, pcm=b"\x00" * 640)
        for index in range(1_000)
    )
    SessionRecorder._prune(window, keep_ms=1_000)
    # the newest frame ends at 20000 ms, so everything ending at or before 19000 goes: 50 frames of
    # 20 ms remain, exactly the keep_ms window
    assert len(window) == 50


def test_a_segment_of_unknown_stream_cannot_be_built() -> None:
    with pytest.raises(ValueError, match="unknown stream"):
        Segment("speaker_3", 0, 100)


def test_the_recorder_refuses_nothing_about_a_closed_capturer_at_start(store: Store) -> None:
    class Broken(FakeCapturer):
        def start(self) -> None:
            raise CapturerError("parec: not found")

    with pytest.raises(CapturerError):
        recorder(store, Broken()).run()


def test_frames_are_cut_on_exactly_the_segment_boundaries(store: Store) -> None:
    # a single stream, speech from frame 0, so the segment is [0, 400)
    script = [(MIC, 0.5)] * 20 + [(MIC, 0.0)] * 45
    transcriber = RecordingTranscriber()
    summary = recorder(store, FakeCapturer(script), transcriber).run()
    assert summary.lines[0].start_ms == 0
    assert summary.lines[0].end_ms == 400
    assert len(transcriber.audio[0]) == 400 // FRAME_MS * 640
